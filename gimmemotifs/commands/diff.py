#!/usr/bin/python
# Copyright (c) 2013-2014 Simon van Heeringen <s.vanheeringen@ncmls.ru.nl>
#
# This module is free software. You can redistribute it and/or modify it under 
# the terms of the MIT License, see the file COPYING included with this 
# distribution.
import sys
import os
import shutil
import numpy as np
from gimmemotifs.config import MotifConfig
from gimmemotifs.genome_index import *
from gimmemotifs.scan import get_counts
from gimmemotifs.motif import pwmfile_to_motifs
from gimmemotifs.fasta import Fasta
from gimmemotifs.plot import diff_plot
from tempfile import mkdtemp

def diff(args):

    infiles = args.inputfiles.split(",")
    bgfile = args.bgfile
    outfile = args.outputfile
    pwmfile = args.pwmfile
    cutoff = args.cutoff
    genome = args.genome
    minenr = float(args.minenr)

    tmpdir = mkdtemp()
    
    # Retrieve FASTA clusters from BED file
    if len(infiles) == 1 and infiles[0].endswith("bed"):
        if not args.genome:
            sys.stderr.write("Can't convert BED file without genome!\n")
            sys.exit(1)

        clusters = {}
        for line in open(infiles[0]):
            vals = line.strip().split("\t")
            clusters.setdefault(vals[3], []).append(vals[:3])
        
        infiles = []
        
        config = MotifConfig()
        index_dir = config.get_index_dir()

        for cluster,regions in clusters.items():
            sys.stderr.write("Creating FASTA file for {0}\n".format(cluster))
            inbed = os.path.join(tmpdir, "{0}.bed".format(cluster))
            outfa = os.path.join(tmpdir, "{0}.fa".format(cluster))
            with open(inbed, "w") as f:
                for vals in regions:
                    f.write("{0}\t{1}\t{2}\n".format(*vals))
            track2fasta(os.path.join(index_dir, genome), inbed, outfa)
            infiles.append(outfa)
    
    pwms = dict([(m.id, m) for m in pwmfile_to_motifs(pwmfile)])
    motifs = [m for m in pwms.keys()]
    names = [os.path.basename(os.path.splitext(f)[0]) for f in infiles]
    
    # Get background frequencies
    nbg = float(len(Fasta(bgfile).seqs))
    bgcounts = get_counts(bgfile, pwms.values(), cutoff)
    bgfreq = [(bgcounts[m] + 0.01) / nbg for m in motifs]
    
    # Get frequences in input files
    freq = {}
    counts = {}
    for fname in infiles:
        c = get_counts(fname, pwms.values(), cutoff)
        n = float(len(Fasta(fname).seqs))
        freq[fname] = [(c[m] + 0.01) / n for m in motifs]
        counts[fname] = [c[m] for m in motifs]
    
    freq = np.array([freq[fname] for fname in infiles]).transpose()
    counts = np.array([counts[fname] for fname in infiles]).transpose()
    
    #for row in freq:
    #    print freq

    diff_plot(motifs, pwms, names, freq, counts, bgfreq, bgcounts, outfile, minenr=minenr)

    shutil.rmtree(tmpdir)
