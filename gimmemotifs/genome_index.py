# Copyright (c) 2009-2010 Simon van Heeringen <s.vanheeringen@ncmls.ru.nl>
#
# This module is free software. You can redistribute it and/or modify it under 
# the terms of the MIT License, see the file COPYING included with this 
# distribution.
""" Module to index genomes for fast retrieval of sequences """

from struct import pack,unpack
from string import maketrans
from glob import glob
import subprocess as sp
import random
import bisect
import sys
import os

def available_genomes(index_dir):
    return [os.path.basename(x) for x in glob(os.path.join(index_dir, "*")) if os.path.isdir(x)]

class GenomeIndex:
    """ Index fasta-formatted files for faster retrieval of sequences
        Typical use:
        
        # Make index
        g = GenomeIndex()
        g.create_index("/usr/share/genomes/hg18", "/usr/share/genome_index/hg18")

        # Retrieve sequence
        g = GenomeIndex("/usr/share/genome_index/hg18")
        seq = g.get_sequence("chr17", "7520037", "7531588")

        # Batch bed-file to fasta-file
        track2fasta("/usr/share/genome_index/hg18", "p53_targets.bed", "p53_targets.fa")
    """
    
    def __init__(self, index_dir=None):
        """ Initialize GenomeIndex with index_dir as optional argument"""
        self.param_file = "index.params"
        self.index_dir = index_dir
        self.fasta_dir = None
        # Fasta extensions
        self.FASTA_EXT = [".fasta", ".fa", ".fsa"]
        
        self.size = {}
        self.fasta_file = {}
        self.index_file = {}
        self.line_size = {}
        self.pack_char = "L"

        if self.index_dir:
            if os.path.exists(os.path.join(self.index_dir, self.param_file)):
                self._read_index_file()
    
    def _check_dir(self, dir):
        """ Check if dir exists, if not: give warning and die"""
        if not os.path.exists(dir):
            print "Directory %s does not exist!" % dir
            sys.exit(1)
    
    def _make_index(self, fasta, index):
        """ Index a single, one-sequence fasta-file"""
        out = open(index, "w")
        f = open(fasta)
        # Skip first line of fasta-file
        line = f.readline()
        offset = f.tell()
        line = f.readline()
        while line:
            out.write(pack(self.pack_char, offset))
            offset = f.tell()
            line = f.readline()
        f.close()
        out.close()

    def create_index(self,fasta_dir=None, index_dir=None):
        """Index all fasta-files in fasta_dir (one sequence per file!) and
        store the results in index_dir"""
        
        # Use default directories if they are not supplied
        if not fasta_dir:
            fasta_dir = self.fasta_dir

        if not index_dir:
            index_dir = self.index_dir

        # Can't continue if we still don't have an index_dir or fasta_dir
        if not fasta_dir:
            print "fasta_dir not defined!"
            sys.exit(1)
        
        if not index_dir:
            print "index_dir not defined!"
            sys.exit(1)
        
        index_dir = os.path.abspath(index_dir)
        fasta_dir = os.path.abspath(fasta_dir)

        self.index_dir = index_dir

        # Prepare index directory
        if not os.path.exists(index_dir):
            try:
                os.mkdir(index_dir)
            except OSError, e:
                if e.args[0] == 13:
                    sys.stderr.write("No permission to create index directory. Superuser access needed?\n")
                    sys.exit()
                else:
                    sys.stderr.write(e)

        # Directories need to exist
        self._check_dir(fasta_dir)
        self._check_dir(index_dir)

        # Get all fasta-files 
        try:
		files = os.listdir(fasta_dir)
        except OSError:
		if os.path.exists(fasta_dir):
			cmd = "find {0} -maxdepth 1 -name \"*\"".format(fasta_dir)
        		p = sp.Popen(cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE)
        		stdout,stderr = p.communicate()
        		files = [os.path.basename(fname) for fname in stdout.splitlines()]
   		else:
        		raise


	
	fastafiles = [os.path.join(fasta_dir, file) for file in files if os.path.splitext(file)[-1] in self.FASTA_EXT]

        if not fastafiles:
            print "No fastafiles found in %s with extension in %s" % (fasta_dir, ",".join(self.FASTA_EXT))
            sys.exit(1)

        # param_file will hold all the information about the location of the fasta-files, indeces and 
        # length of the sequences
        param_file = os.path.join(index_dir, self.param_file)
        
        try:
            out = open(param_file, "w")
        except IOError, e:
                if e.args[0] == 13:
                    sys.stderr.write("No permission to create files in index directory. Superuser access needed?\n")
                    sys.exit()
                else:
                    sys.stderr.write(e)

        
        for fasta_file in fastafiles:
            #sys.stderr.write("Indexing %s\n" % fasta_file)
            f = open(fasta_file)
            line = f.readline()
            if not line.startswith(">"):
                sys.stderr.write("%s is not a valid FASTA file, expected > at first line\n" % fasta_file)
                sys.exit()
            
            seqname = line.strip().replace(">", "")
            line = f.readline()
            line_size = len(line.strip())

            total_size = 0 
            while line:
                line = line.strip()
                if line.startswith(">"):
                    sys.stderr.write("Sorry, can only index genomes with one sequence per FASTA file\n%s contains multiple sequences\n" % fasta_file)
                    sys.exit()
                
                total_size += len(line)
                line = f.readline()

            index_file = os.path.join(index_dir, "%s.index" % seqname)

            out.write("%s\t%s\t%s\t%s\t%s\n" % (seqname, fasta_file, index_file, line_size, total_size))
            
            self._make_index(fasta_file, index_file)
            f.close()
        out.close()

        # Read the index we just made so we can immediately use it
        self._read_index_file()
    
    def _read_index_file(self):
        """read the param_file, index_dir should already be set """
        param_file = os.path.join(self.index_dir, self.param_file)
        for line in open(param_file).readlines():
            (name, fasta_file, index_file, line_size, total_size) = line.strip().split("\t")
            self.size[name] = int(total_size)
            self.fasta_file[name] = fasta_file
            self.index_file[name] = index_file
            self.line_size[name] = int(line_size)

    def _read_seq_from_fasta(self, fasta, offset, nr_lines):
        """ retrieve a number of lines from a fasta file-object, starting at offset"""
        fasta.seek(offset)
        lines = [fasta.readline().strip() for i in range(nr_lines)]
        return "".join(lines)

    def _get_offset_from_index(self, index, offset):    
        size = len(pack(self.pack_char, 0))
        index.seek(offset)
        entry = index.read(size)
        d_offset = unpack(self.pack_char, entry)[0]
        return d_offset
        
    def _make_gc_windows(self, fname, fasta, window):
        f = open(fname, "w")
        pc = float(window) / 100
        for chrom, seq in fasta.items():
            for i in range(0, len(seq), window):
                subseq = seq[i: i + window].upper()
                if subseq.count("N") < window / 4:
                    gc = int((subseq.count("G") + subseq.count("C")) / pc)
                    f.write("%s\t%s\t%s\n" % (chrom, i, gc))

        f.close()
                
    
    def _read(self, index, fasta, start, end, line_size):
        #start = start - 1
        start_line = int(start / line_size)  
        size = len(pack(self.pack_char, 0))
        nr_lines = (end - start) / line_size + 2 
        i_offset = size * (start_line)
        #print start
        #print start_line
        #print size
        #print nr_lines
        #print i_offset
        
        d_offset = self._get_offset_from_index(index, i_offset)
        seq = self._read_seq_from_fasta(fasta, d_offset, nr_lines)
        #print start, nr_lines, line_size, end
        #print start - (nr_lines - 2) * line_size, end - start
        #print seq
        length = end - start 
        start = start - start_line  * line_size 
        seq = seq[start: start + length ]
        #print seq
        #print
        return seq
    
    def get_sequences(self, chr, coords):
        """ Retrieve multiple sequences from same chr (RC not possible yet)"""    
        # Check if we have an index_dir
        if not self.index_dir:
            print "Index dir is not defined!"
            sys.exit()

        # retrieve all information for this specific sequence
        fasta_file = self.fasta_file[chr]
        index_file = self.index_file[chr]
        line_size = self.line_size[chr]
        total_size = self.size[chr]
        index = open(index_file)
        fasta = open(fasta_file)
        
        seqs = []
        for coordset in coords:
            seq = ""
            for (start,end) in coordset: 
                if start > total_size:
                    raise ValueError, "%s: %s, invalid start, greater than sequence length!" % (chr,start)
            
                if start < 0:
                    raise ValueError, "Invalid start, < 0!"
                
                if end > total_size:
                    raise ValueError, "Invalid end, greater than sequence length!"


                seq += self._read(index, fasta, start, end, line_size)
            seqs.append(seq)
        index.close()
        fasta.close()

        return seqs


    def get_sequence(self, chr, start, end, strand=None):
        """ Retrieve a sequence """    
        # Check if we have an index_dir
        if not self.index_dir:
            print "Index dir is not defined!"
            sys.exit()

        # retrieve all information for this specific sequence
        fasta_file = self.fasta_file[chr]
        index_file = self.index_file[chr]
        line_size = self.line_size[chr]
        total_size = self.size[chr]

        #print fasta_file, index_file, line_size, total_size
        if start > total_size:
            raise ValueError, "Invalid start {0}, greater than sequence length {1} of {2}!".format(start, total_size, chr)
        
        if start < 0:
            raise ValueError, "Invalid start, < 0!"
        
        if end > total_size:
            raise ValueError, "Invalid end {0}, greater than sequence length {1} of {2}!".format(end, total_size, chr)


        index = open(index_file)
        fasta = open(fasta_file)
        seq = self._read(index, fasta, start, end, line_size)
        index.close()
        fasta.close()

        if strand and strand == "-":
            seq = rc(seq)
        return seq

    def get_chromosomes(self):
        """ Return all sequences in the index """
        return self.index_file.keys()

    def get_size(self, chr=None):
        """ Return the sizes of all sequences in the index, or the size of chr if specified
        as an optional argument """
        if chr:
            return self.size[chr]

        total = 0
        for size in self.size.values():
            total += size

        return total 

def rc(seq):
    """ Return reverse complement of sequence """
    d = maketrans("actgACTG","tgacTGAC")
    return seq[::-1].translate(d)

def track2fasta(index_dir, bedfile, fastafile, extend_up=0, extend_down=0, use_strand=False):
    """ Convert a bedfile to a fastafile, given a certain index """
    try:
        g = GenomeIndex(index_dir)
    except:
        # For parallel python
        g = gimmemotifs.genome_index.GenomeIndex(index_dir)
    
    BUFSIZE = 10000
    f = open(bedfile)
    lines = f.readlines(BUFSIZE)
    line_count = 0
    features = []
    chr_features = {}
    while lines:
        for line in lines:
            line_count += 1
            if not line.startswith("#") and not line.startswith("track"):
                vals = line.strip().split("\t")
                try:
                    start, end = int(vals[1]), int(vals[2])
                except:
                    print "Error on line %s while reading %s. Is the file in BED or WIG format?" % (line_count, bedfile)
                    sys.exit(1)
                strand = "+"
                if use_strand:
                    try:
                        strand = vals[5]
                    except:
                        strand = "+"
                chrom = vals[0]
                val = "" 
                if len(vals) > 3:
                    val = vals[3]
                if len(vals) == 12:
                    # BED12
                    blockSizes = [int(x) for x in vals[10].split(",")[:-1]]
                    blockStarts = [int(x) for x in vals[11].split(",")[:-1]]
                    chr_features.setdefault(chrom,[]).append([])
                    for estart,esize in zip(blockStarts, blockSizes):
                        chr_features[chrom][-1].append([start + estart, 
                                                        start + estart + esize,
                                                        val,
                                                        strand
                                                       ])

                else:
                    chr_features.setdefault(chrom,[]).append([[start,end,val,strand]])    
                features.append([chrom, len(chr_features[chrom]) - 1])
        lines = f.readlines(BUFSIZE)
    f.close()
    
    seqs = {}
    for chrom,feats in chr_features.items():
        size = g.get_size(chrom)
        feats = [f for f in feats if len(f) > 0] 
        for f in feats:
            f[0][0] -= extend_up
            if f[0][0] < 0:
                f[0][0] = 0
            f[-1][1] += extend_down
            if f[-1][1] > size:
                f[-1][1] = size
 
        coords = [[[x[0], x[1]] for x in f] for f in feats]
        all_seqs = g.get_sequences(chrom, coords)
       
        gene_ext_coords = [[f[0][0], f[-1][1], f[0][2], f[0][3]] for f in feats]
        
        for (ext_start, ext_end, val, strand), (seq), i in zip(gene_ext_coords, all_seqs, range(len(feats))):
            seqs[(chrom,i)] = [seq, ext_start, ext_end, val, strand]
    
    out = open(fastafile, "w")
    for chrom, i in features:
        seq, ext_start, ext_end, val, strand = seqs[(chrom, i)]
        if use_strand and strand == "-":
            seq = rc(seq)
        if val:
            out.write(">%s:%s-%s %s\n%s\n" % (chrom, ext_start, ext_end, val, seq))
        else:
            out.write(">%s:%s-%s\n%s\n" % (chrom, ext_start, ext_end, seq))
    out.close()

def _weighted_selection(l, n):
    """
        Selects  n random elements from a list of (weight, item) tuples.
        Based on code snippet by Nick Johnson
    """
    cuml = []
    items = []
    total_weight = 0.0
    for weight, item in l:
        total_weight += weight
        cuml.append(total_weight)
        items.append(item)
    
    return [items[bisect.bisect(cuml, random.random()*total_weight)] for x in range(n)]

def get_random_sequences(index_dir, n=10, length=200, chroms=None):
    g = GenomeIndex(index_dir)
    if not chroms:
        chroms = g.get_chromosomes()

    sizes = dict([(x, g.get_size(x)) for x in g.get_chromosomes()])


    l = [(sizes[x], x) for x in g.get_chromosomes() if sizes[x] > length and x in chroms]
    
    chroms = _weighted_selection(l, n)
    coords = [(x, int(random.random() * (sizes[x] - length))) for x in chroms]
    return [(x[0], x[1], x[1] + length) for x in coords]

if __name__ == "__main__":
    # If run directly this script will index a directory of fasta-files
    from optparse import OptionParser

    DEFAULT_INDEX = '/usr/share/py_genome_index/'
    parser = OptionParser()
    parser.add_option("-i", "--indexdir", dest="indexdir", help="Index dir (default %s)" % DEFAULT_INDEX, metavar="DIR", default=DEFAULT_INDEX)
    parser.add_option("-f", "--fastadir", dest="fastadir", help="Directory containing fastafiles", metavar="DIR")
    parser.add_option("-n", "--indexname", dest="indexname", help="Name of index", metavar="NAME")
    
    (options, args) = parser.parse_args()

    if not options.fastadir or not options.indexname:
        parser.print_help()
        sys.exit(1)
    
    if not os.path.exists(options.indexdir):
        print "Index_dir %s does not exist!" % (options.indexdir)
        sys.exit(1)

    fasta_dir = options.fastadir
    index_dir = os.path.join(options.indexdir, options.indexname)

    g = GenomeIndex()
    g = g.create_index(fasta_dir, index_dir)
