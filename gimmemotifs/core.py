# Copyright (c) 2009-2013 Simon van Heeringen <s.vanheeringen@ncmls.ru.nl>
#
# This module is free software. You can redistribute it and/or modify it under 
# the terms of the MIT License, see the file COPYING included with this 
# distribution.
""" This module contains the core GimmeMotifs functionality """

# Python imports
import os
import sys
import shutil
import logging
import logging.handlers
from datetime import datetime
from numpy import median

# External imports
import kid
from scipy.stats.mstats import rankdata

# GimmeMotifs imports
from gimmemotifs.config import *
from gimmemotifs.fasta import *
from gimmemotifs.utils import *
from gimmemotifs.background import *
from gimmemotifs.comparison import *
from gimmemotifs import genome_index
from gimmemotifs.cluster import *
from gimmemotifs.plot import *
from gimmemotifs import mytmpdir

def job_server_ok():
    return True

def get_scores(motif, fg_file, bg_file):
    error = None
    auc = None
    mncp = None
    max_f = None
    y = None
    try:
        from gimmemotifs.fasta import Fasta
        from gimmemotifs.rocmetrics import ROC_values,ROC_AUC,MNCP,max_fmeasure

        fg_result = motif.pwm_scan_score(Fasta(fg_file), cutoff=0.0, nreport=1)
        fg_vals = [sorted(x)[-1] for x in fg_result.values()]

        bg_result = motif.pwm_scan_score(Fasta(bg_file), cutoff=0.0, nreport=1)
        bg_vals = [sorted(x)[-1] for x in bg_result.values()]

        (x, y) = ROC_values(fg_vals, bg_vals)
        auc = ROC_AUC(fg_vals, bg_vals)
        mncp = MNCP(fg_vals, bg_vals)
        max_f, y = max_fmeasure(x,y)

    except Exception,e:
        error = e
    return (error, auc, mncp, max_f, y)

def get_roc_values(motif, fg_file, bg_file):
    error = None
    x = []
    y = []
    try:
        from gimmemotifs.fasta import Fasta
        from gimmemotifs.rocmetrics import ROC_values,ROC_AUC,MNCP,max_fmeasure
    
        fg_result = motif.pwm_scan_score(Fasta(fg_file), cutoff=0.0, nreport=1)
        fg_vals = [sorted(x)[-1] for x in fg_result.values()]
    
        bg_result = motif.pwm_scan_score(Fasta(bg_file), cutoff=0.0, nreport=1)
        bg_vals = [sorted(x)[-1] for x in bg_result.values()]
    
        (x, y) = ROC_values(fg_vals, bg_vals)
    except Exception,e:
        error = e
    return error,x,y


class GimmeMotifs:
    NAME = "gimme_motifs"
    SCAN_THRESHOLD = "0.9"

    def __init__(self, name=None):
        self.config = MotifConfig()
        self.server = None

        if not name:
            name = "%s_%s" % (self.NAME, datetime.today().strftime("%d_%m_%Y"))
        self.name = name

        # create a directory for all the intermediate and output files
        self._setup_output_dir(name)
        
        # setup logging
        self._setup_logging()    
        self.logger.info("%s version %s" % (self.NAME, GM_VERSION))
        self.logger.info("Created output directory %s (all output files will be stored here)" % self.outdir)

        # setup the names of the intermediate and output files
        self._setup_filenames()

        # check for parallel python
        self.parallel = self._is_parallel_enabled()
        if self.parallel:
            self.logger.debug("Parallel Python is installed")
        else:
            self.logger.info("Couldn't find Parallel Python! I will continue, but installing pp will signifcantly speed up your analysis!")
    
    def job_server(self):
        try:
            self.server.submit(job_server_ok)
        except:    
                self.server = self._get_job_server()
        return self.server

    def _setup_output_dir(self, name):

        if os.path.exists(name):
            sys.stderr.write("Output directory %s already exists!\n" % name)
            sys.stderr.write("Resuming a previous run is not yet implemented. Please specify a different name,\n")
            sys.stderr.write("or delete this directory if you really want to overwrite it\n")
            #sys.exit(1)
        else:
            try:
                os.mkdir(name)
            except:
                sys.stderr.write("Can't create output directory %s!\n" % name)
                #sys.exit(1)
        
        self.outdir = name
        self.tmpdir = os.path.join(self.outdir, "intermediate_results")
        self.imgdir = os.path.join(self.outdir, "images")
        try:
            os.mkdir(self.tmpdir)
            os.mkdir(self.imgdir)
        except:
            pass
        star = os.path.join(self.config.get_template_dir(), "star.png")
        shutil.copyfile(star, os.path.join(self.imgdir, "star.png"))    

    def _setup_logging(self):
        self.logger = logging.getLogger('motif_analysis')
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = 0

        # nice format
        file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        screen_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        # Log to file
        logfile = os.path.join(self.name, "%s.log" % self.NAME)
        fh = logging.FileHandler(logfile, "w")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(file_formatter)
        self.logger.addHandler(fh)

        # Log to screen
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(screen_formatter)
        self.logger.addHandler(sh)

        self.logger.info("Logging started")
        self.logger.info("Created logfile %s" % logfile)

    def _setup_filenames(self):
        # Um yes, there is a smarter way, I'm sure! ;)
        self.input_bed = os.path.join(self.tmpdir, "%s_peakinputfile.bed" % self.name)

        self.prediction_bed    = os.path.join(self.tmpdir, "%s_prediction.bed" % self.name)
        self.prediction_fa = os.path.join(self.tmpdir, "%s_prediction.fa" % self.name)
        self.prediction_bg = os.path.join(self.tmpdir, "%s_prediction_background.fa" % self.name)
        
        self.validation_bed = os.path.join(self.tmpdir, "%s_validation.bed" % self.name)
        self.validation_fa = os.path.join(self.tmpdir, "%s_validation.fa" % self.name)
        self.validation_gff = os.path.join(self.tmpdir, "%s_validation.gff" % self.name)
        
        self.predicted_pfm = os.path.join(self.tmpdir, "%s_all_motifs.pfm" % self.name)

        self.significant_pfm = os.path.join(self.tmpdir, "%s_significant_motifs.pfm" % self.name)
        
        self.location_fa = os.path.join(self.tmpdir, "%s_validation_500.fa" % self.name)
        self.location_pfile = os.path.join(self.tmpdir, "%s_localization_pvalue.txt" % self.name)
        self.stats_file = os.path.join(self.tmpdir, "%s_stats.txt" % self.name)
        self.ranks_file = os.path.join(self.tmpdir, "%s_ranks.txt" % self.name)

        #self.cluster_dir = os.path.join(self.outdir, "cluster_report")
        self.validation_cluster_gff = os.path.join(self.tmpdir, "%s_validation_clustered.gff" % self.name)
        self.cluster_pwm = os.path.join(self.tmpdir, "%s_clustered_motifs.pwm" % self.name)
        self.final_pwm = os.path.join(self.outdir, "%s_motifs.pwm" % self.name)
        self.cluster_report = os.path.join(self.outdir, "%s_cluster_report.html" % self.name)
        self.motif_report = os.path.join(self.outdir, "%s_motif_report.html" % self.name)
        self.text_report = os.path.join(self.outdir, "%s_motif_report.tsv" % self.name)
        self.params_file = os.path.join(self.outdir, "%s_params.txt" % self.name)

        # Data structures to hold the background file locations
        ftypes = {
            "bed": ".bed",
            "fa": ".fa",
            "gff": ".gff",
            "enrichment": "_enrichment.txt",
            "roc": "_significant_motifs_roc_metrics.txt",
            "cluster_gff": "_clustered.gff",
            "cluster_enrichment": "_enrichment_clustered.txt",
            "cluster_roc": "_roc_metrics_clustered.txt"
        }
        
        self.bg_file = dict([(t,{}) for t in ftypes.keys()])
        
        for bg in (FA_VALID_BGS + BED_VALID_BGS):
            for ftype, extension in ftypes.items():
                self.bg_file[ftype][bg] =  os.path.join(self.tmpdir, "%s_bg_%s%s" % (self.name, bg, extension))

    def _is_parallel_enabled(self):
        try:
            import pp
            return True
        except:
            return False

    def _get_job_server(self):
        self.logger.debug("Creating parallel python job server")
        import pp
        server = pp.Server(secret="pumpkinrisotto")
        ncpus = int(self.params["ncpus"])
        if server.get_ncpus() > ncpus:
            server.set_ncpus(ncpus)
        return server

    def _check_input(self, file):
        """ Check if the inputfile is a valid bed-file """
        if not os.path.exists(file):    
            self.logger.error("Inputfile %s does not exist!" % file)
            sys.exit(1)
        
        for i, line in enumerate(open(file)):
            if line.startswith("#") or line.startswith("track") or line.startswith("browser"):
                # comment or BED specific stuff
                pass
            else:
                vals = line.strip().split("\t")
                if len(vals) < 3:
                    self.logger.error("Expecting tab-seperated values (chromosome<tab>start<tab>end) on line %s of file %s" % (i + 1, file))
                    sys.exit(1)
                try:
                    start, end = int(vals[1]), int(vals[2])
                except:
                    self.logger.error("No valid integer coordinates on line %s of file %s" % (i + 1, file))
                    sys.exit(1)
                if len(vals) > 3:
                    try:
                        float(vals[3])
                    except:
                        pass
                        #self.logger.warn("No numerical value in column 4 on line %s of file %s, ignoring..." % (i + 1, file))

    def prepare_input_bed(self, inputfile, organism="hg18", width=200, fraction=0.2, abs_max=1000, use_strand=False):
        """ Create all the bed- and fasta-files necessary for motif prediction and validation """    
        self.inputfile = inputfile

        width = int(width)
        fraction = float(fraction)
        abs_max = int(abs_max)
        use_strand = bool(use_strand)

        self.logger.info("Preparing input (BED)")
        
        # Set all peaks to specific width
        self.logger.debug("Creating inputfile %s, width %s" % (self.input_bed, width))
        
    #    if not self.weird:
        write_equalwidth_bedfile(inputfile, width, self.input_bed)
        
        # Split input_bed in prediction and validation set 
        self.logger.debug("Splitting %s into prediction set (%s) and validation set (%s)" % (self.input_bed, self.prediction_bed, self.validation_bed))
        #if not self.weird:
        self.prediction_num, self.validation_num = divide_file(self.input_bed, self.prediction_bed, self.validation_bed, fraction, abs_max)
        
        
        # Make fasta files    
        index_dir = os.path.join(self.config.get_index_dir(), organism)
        self.logger.debug("Creating %s" % (self.prediction_fa))
        
        genome_index.track2fasta(index_dir, self.prediction_bed, self.prediction_fa, use_strand=use_strand)
        self.logger.debug("Creating %s" % (self.validation_fa))
        genome_index.track2fasta(index_dir, self.validation_bed, self.validation_fa, use_strand=use_strand)

    def prepare_input_fa(self, inputfile, width=200, fraction=0.2, abs_max=1000):
        """ Create all the bed- and fasta-files necessary for motif prediction and validation """    
        self.inputfile = inputfile

        width = int(width)
        fraction = float(fraction)
        abs_max = int(abs_max)

        self.logger.info("Preparing input (FASTA)")
        
        # Split inputfile in prediction and validation set 
        self.logger.debug("Splitting %s into prediction set (%s) and validation set (%s)" % (self.inputfile, self.prediction_fa, self.validation_fa))
            
        self.prediction_num, self.validation_num = divide_fa_file(self.inputfile, self.prediction_fa, self.validation_fa, fraction, abs_max)


    def _create_background(self, bg_type, bedfile, fafile, outfile, organism="hg18", width=200, nr_times=10):
        if bg_type == "random":
            if int(self.markov_model) >= 6:
                self.logger.warn("Are you sure about the Markov model? It seems too high!")
            else:
                order = {"1":"1st","2":"2nd", "3":"3rd", "4":"4th", "5":"5th"}[str(self.markov_model)]
                self.logger.info("Creating random background (%s order Markov)" % order)
        
            f = Fasta(fafile)
            m = MarkovFasta(f, k=int(self.markov_model))
            m.writefasta(outfile)
            self.logger.debug("Random background: %s" % (outfile))
            # return the number of random sequences created
            return len(m)
        elif bg_type == "genomic_matched":    
            gene_file = os.path.join(self.config.get_gene_dir(), "%s.bed" % organism)
            index_dir = os.path.join(self.config.get_index_dir(), organism)
            self.logger.info("Creating matched genomic background (%s, using genes in %s)" % (organism, gene_file))
        
            f = MatchedGenomicFasta(bedfile, gene_file, index_dir, width, nr_times)
            f.writefasta(outfile)
            self.logger.debug("Matched genomic background: %s" % (outfile))
            return len(f)
        elif bg_type == "promoter":
            gene_file = os.path.join(self.config.get_gene_dir(), "%s.bed" % organism)
            index_dir = os.path.join(self.config.get_index_dir(), organism)
            
            self.logger.info("Creating random promoter background (%s, using genes in %s)" % (organism, gene_file))
            fg = Fasta(fafile)
            f = PromoterFasta(gene_file, index_dir, width, nr_times * len(fg))
            f.writefasta(outfile)
            self.logger.debug("Random promoter background: %s" % (outfile))
            return len(f)
        elif bg_type == "user":
            bg_file = self.params["user_background"]
            if not os.path.exists(bg_file):
                self.logger.error("User-specified background file %s does not exist!" % bg_file)
                sys.exit(1)
            else:
                self.logger.info("Copying user-specified background file %s to %s." % (bg_file, outfile))
                fa = Fasta(bg_file)
                l = median([len(seq) for seq in fa.seqs])
                if l < width * 0.95 or l > width * 1.05:
                    self.logger.warn("The user-specified background file %s contains sequences with a median length of %s, while GimmeMotifs predicts motifs in sequences of length %s. This will influence the statistics! It is recommended to use background sequences of the same length." % (bg_file, l, width))
                fa.writefasta(outfile)
                return len(fa)

#    def filter_motifs(self, motif_ids, enrichmentfile, e_cutoff, p_cutoff):
#        filt_motifs = []
#        for line in open(enrichmentfile).readlines():
#            if not line.startswith("#"):
#                vals = line.strip().split("\t")
#                if vals[0] in motif_ids:
#                    p,e = float(vals[2]), float(vals[5])
#                    if p <= p_cutoff and e >= e_cutoff:
#                        filt_motifs.append(vals[0])
#        return filt_motifs


    def calculate_enrichment(self, motif_file, fg, bg):
        """ fg: [sample_fa, sample_gff] bg: [[bg1_fa, bg1_gff, bg1_enrichment], [bg2_fa, bg2_gff, bg2_enrichment], .. etc] """
        
        self.logger.info("Scanning background sequences with motifs")
        scan_cmd = scan_fasta_file_with_motifs
        jobs = []
        if self.parallel:
            jobs.append(self.job_server().submit(scan_cmd, (fg[0], motif_file, self.SCAN_THRESHOLD, fg[1],), (),()))
        else:
            scan_cmd(fg[0], motif_file, self.SCAN_THRESHOLD, fg[1])

        for fasta_file, gff_file in [x[:2] for x in bg]:
            if self.parallel:
                jobs.append(self.job_server().submit(scan_cmd, (fasta_file, motif_file, self.SCAN_THRESHOLD, gff_file,), (),()))
            else:
                scan_cmd(fasta_file, motif_file, self.SCAN_THRESHOLD, gff_file)
            
        for job in jobs:
                error = job()
                if error:
                    self.logger.error("Error in thread: %s" % error)
                    sys.exit(1)

        self.logger.info("Calculating enrichment")
        enrichment_cmd = gff_enrichment
        num_sample = len(Fasta(fg[0]).items())    
        for fasta_file, gff_file, out_file in bg:
            num_bg = len(Fasta(fasta_file).items())
            enrichment_cmd(fg[1], gff_file, num_sample, num_bg, out_file)

    def create_background(self, background=["random"], organism="hg18", width=200):
        nr_sequences = {}
        
        # Create background for motif prediction
        if "genomic_matched" in background:
            self._create_background("genomic_matched", self.validation_bed, None, self.prediction_bg, organism=organism, width=width)
        # This is not ideal, but for genomes where matched_genomic cannot be used...
        else:
            self._create_background(background[0], self.validation_bed, self.validation_fa, self.prediction_bg, organism=organism, width=width)

        # Get background fasta files
        for bg in background:
            nr_sequences[bg] = self._create_background(bg, self.validation_bed, self.validation_fa, self.bg_file["fa"][bg], organism=organism, width=width)

    def _cluster_motifs(self, pfm_file, cluster_pwm, dir, threshold):
        self.logger.info("Clustering significant motifs.")
        
        trim_ic = 0.2
        clusters = []
        motifs = pwmfile_to_motifs(pfm_file)
        if len(motifs) == 1:
            clusters = [[motifs[0], motifs]]
        else:
            tree = cluster_motifs(pfm_file, "total", "wic", "mean", True, threshold=float(threshold), include_bg=True)
            clusters = tree.getResult()

        ids = []
        mc = MotifComparer()

        for cluster,members in clusters:
            cluster.trim(trim_ic)
            cluster.to_img(os.path.join(self.imgdir,"%s.png" % cluster.id), format="PNG")
            ids.append([cluster.id, {"src":"images/%s.png" % cluster.id},[]])
            if len(members) > 1:
                scores = {}
                for motif in members:
                    scores[motif] =  mc.compare_motifs(cluster, motif, "total", "wic", "mean", pval=True)    
                add_pos = sorted(scores.values(),cmp=lambda x,y: cmp(x[1], y[1]))[0][1]
                for motif in members:
                    score, pos, strand = scores[motif]
                    add = pos - add_pos
                        
                    if strand in [1,"+"]:
                        pass
                    else:
                        #print "RC %s" % motif.id
                        rc = motif.rc()
                        rc.id = motif.id
                        motif = rc
                    #print "%s\t%s" % (motif.id, add)    
                    motif.to_img(os.path.join(self.imgdir, "%s.png" % motif.id.replace(" ", "_")), format="PNG", add_left=add)
            ids[-1][2] = [dict([("src", "images/%s.png" % motif.id.replace(" ", "_")), ("alt", motif.id.replace(" ", "_"))]) for motif in members]
        
        kid.enable_import()
        template_file = os.path.join(self.config.get_template_dir(), "cluster_template_v2.kid")
        template = kid.Template(file=template_file, expname=self.name, motifs=ids, inputfile=self.inputfile, date=datetime.today().strftime("%d/%m/%Y"), version=GM_VERSION)
        f = open(self.cluster_report, "w")
        f.write(template.serialize())
        f.close()
        
        f = open(cluster_pwm, "w")
        if len(clusters) == 1 and len(clusters[0][1]) == 1:
            f.write("%s\n" % clusters[0][0].to_pwm())
        else:
            for motif in tree.get_clustered_motifs():
                f.write("%s\n" % motif.to_pwm())
        f.close()
    
        self.logger.info("Clustering done. See the result in %s" % self.cluster_report)
        return clusters

    def create_roc_plots(self, pwm_file, fg_fasta, bg_fasta, name):
        motifs = dict([(m.id, m) for m in pwmfile_to_motifs(pwm_file)])
        
        jobs = {}
        for id,m in motifs.items():
            jobs[id] = self.job_server().submit(get_roc_values, (motifs[id],fg_fasta,bg_fasta,))
    
        roc_img_file = os.path.join(self.imgdir, "%s_%s_roc.png")
        
        for id in motifs.keys():
            error, x, y = jobs[id]()
            if error:
                self.logger.error("Error in thread: %s" % error)
                sys.exit(1)

            roc_plot(roc_img_file % (id,name), x, y)

    def calculate_cluster_enrichment(self, pwm, background):
        fg = [self.validation_fa, self.validation_cluster_gff]
        bg = [[self.bg_file["fa"][bg_id], self.bg_file["gff"][bg_id], self.bg_file["cluster_enrichment"][bg_id]] for bg_id in background]
        self.calculate_enrichment(pwm, fg, bg)
        pass


    def _roc_metrics(self, pwm, sample_fa, bg_fa, roc_file):
        motifs = dict([(m.id, m) for m in pwmfile_to_motifs(pwm)])
        
        jobs = {}
        for id,m in motifs.items():
            jobs[id] = self.job_server().submit(get_scores, (motifs[id],sample_fa,bg_fa,))
        
        all_auc = {}
        all_mncp = {}
        f = open(roc_file, "w")
        f.write("Motif\tROC AUC\tMNCP\tMax f-measure\tSens @ max f-measure\n")
        for id in motifs.keys():
            error, auc, mncp, max_f, y = jobs[id]()
            if error:
                self.logger.error("Error in thread: %s" % error)
                sys.exit(1)
            f.write("%s\t%s\t%s\t%s\t%s\n" % (id,auc,mncp,max_f,y))
            all_auc[id] = auc
            all_mncp[id] = mncp
        
        f.close()
        
        return all_auc,all_mncp

    def _calc_report_values(self, pwm, background):
        self.logger.info("Calculating final statistics for report")
        self.p = dict([(b,{}) for b in background])
        self.e = dict([(b,{}) for b in background])

        e_files = dict([(bg, self.bg_file["cluster_enrichment"][bg]) for bg in background])

        for bg in self.p.keys():
            for line in open(e_files[bg]).readlines():
                if not (line.startswith("#") or line.startswith("Motif\tSig")):
                    vals = line.strip().split("\t")
                    self.p[bg][vals[0]] = float(vals[2])
                    self.e[bg][vals[0]] = float(vals[5])
            
        self.auc = dict([(b,{}) for b in background])
        self.mncp = dict([(b,{}) for b in background])
        
        
        rocs = dict([(bg, [self.bg_file["fa"][bg], self.bg_file["roc"][bg]]) for bg in background])
        
        for bg in self.auc.keys():
            bg_fasta_file, roc_file = rocs[bg]
            self.auc[bg], self.mncp[bg] = self._roc_metrics(pwm, self.validation_fa, bg_fasta_file, roc_file)
    
        motifs = pwmfile_to_motifs(pwm)
        self.closest_match = self.determine_closest_match(motifs)
        
    def _create_text_report(self, pwm, background):
        self.logger.info("Creating text report")
        motifs = pwmfile_to_motifs(pwm)

        sort_key = background[0]
        if "genomic_matched" in background:
            sort_key = "genomic_matched"

        f = open(self.text_report, "w")
        header = "ID\tconsensus\tBest match db\tp-value best match\t" + "\t".join("Enrichment (%s)\tp-value (%s)\tROC AUC (%s)\tMNCP (%s)" % (b,b,b,b) for b in background)
        #print header
        f.write("%s\n" % header)
        for motif in sorted(motifs, cmp=lambda x,y: cmp(self.mncp[sort_key][y.id], self.mncp[sort_key][x.id])):
            vals = [motif.id, motif.to_consensus(), self.closest_match[motif.id][0].id, self.closest_match[motif.id][1]]
            for bg in background:
                vals += [self.e[bg][motif.id], self.p[bg][motif.id], self.auc[bg][motif.id], self.mncp[bg][motif.id]]
            f.write("%s\n" % "\t".join([str(x) for x in vals]))
            #print "%s\n" % "\t".join([str(x) for x in vals])
        f.close()    

    def print_params(self):
        f = open(self.params_file, "w")
        for param, value in self.params.items():
            f.write("%s\t%s\n" % (param, value))
        f.close()

    def _create_report(self, pwm, background, stats={}, best_id={}):
        self.logger.info("Creating graphical report")
        class ReportMotif:
            pass
        
        motifs = pwmfile_to_motifs(pwm)
        for m,match in self.closest_match.items():
            match[0].to_img(os.path.join(self.imgdir,"%s.png" % match[0].id), format="PNG")

        sort_key = background[0]
        if "genomic_matched" in background:
            sort_key = "genomic_matched"

        roc_img_file = "%s_%s_roc"
        report_motifs = []
        sorted_motifs = sorted(motifs, 
                cmp= lambda x,y: cmp(self.mncp[sort_key][y.id], self.mncp[sort_key][x.id])
                )

        for motif in motifs:
            rm = ReportMotif()
            rm.id = motif.id
            rm.id_href = {"href": "#%s" % motif.id}
            rm.id_name = {"name": motif.id}
            rm.img = {"src":  os.path.join("images", "%s.png" % motif.id)}
            
            rm.best = best_id[motif.id]
            
            rm.consensus = motif.to_consensus()
            rm.stars = stats["%s_%s" % (motif.id, motif.to_consensus())]["stars"]

            rm.bg = {}
            for bg in background:
                rm.bg[bg] = {}
                rm.bg[bg]["e"] = "%0.2f" % self.e[bg].setdefault(motif.id, 0.0)
                rm.bg[bg]["p"] = "%0.2f" % self.p[bg].setdefault(motif.id, 1.0)
                rm.bg[bg]["auc"] = "%0.3f" % self.auc[bg][motif.id]
                rm.bg[bg]["mncp"] = "%0.3f" % self.mncp[bg][motif.id]
                rm.bg[bg]["roc_img"] = {"src": "images/" + os.path.basename(roc_img_file % (motif.id, bg)) + ".png"}
                rm.bg[bg]["roc_img_link"] = {"href": "images/" + os.path.basename(roc_img_file % (motif.id, bg)) + ".png"}
            
            rm.histogram_img = {"data":"images/%s_histogram.svg" % motif.id}
            rm.histogram_link= {"href":"images/%s_histogram.svg" % motif.id}
            rm.match_img = {"src":  "images/%s.png" % self.closest_match[motif.id][0].id}
            rm.match_id = self.closest_match[motif.id][0].id
            rm.match_pval = "%0.2e" % self.closest_match[motif.id][1] 
            
            report_motifs.append(rm)
        
        total_report = self.motif_report 
        kid.enable_import()
        template_file = os.path.join(self.config.get_template_dir(), "report_template_v2.kid") 
        template = kid.Template(file=template_file, expname=self.name, motifs=report_motifs, inputfile=self.inputfile, date=datetime.today().strftime("%d/%m/%Y"), version=GM_VERSION)
        f = open(total_report, "w")
        f.write(template.serialize())
        f.close()

    def determine_closest_match(self, motifs):
        self.logger.info("Determining closest matching motifs in database (JASPAR)")
        motif_db = self.config.get_default_params()["motif_db"]
        db = os.path.join(self.config.get_motif_dir(), motif_db)
        db_motifs = []
        if db.endswith("pwm") or db.endswith("pfm"):
        
            db_motifs = pwmfile_to_motifs(db)
        elif db.endswith("transfac"):
            db_motifs = transfac_to_motifs(db)
        
        closest_match = {}
        mc = MotifComparer()
        db_motif_lookup = dict([(m.id, m) for m in db_motifs])
        match = mc.get_closest_match(motifs, db_motifs, "partial", "wic", "mean", parallel=False)
        for motif in motifs:
            # Calculate p-value
            pval, pos, orient = mc.compare_motifs(motif, db_motif_lookup[match[motif.id][0]], "partial", "wic", "mean", pval=True)
            closest_match[motif.id] = [db_motif_lookup[match[motif.id][0]], pval]
        return closest_match

    def _determine_best_motif_in_cluster(self, clusters, pwm, sample_fa, bg_fa, imgdir=None):
        num_cluster = {}
        best_id = {}
        out = open(pwm, "w")
        for i, (clus, singles) in enumerate(clusters):
            motifs = [clus] + singles
            tmp = NamedTemporaryFile(dir=mytmpdir())
            tmp2 = NamedTemporaryFile(dir=mytmpdir())
            for m in motifs:
                tmp.write("%s\n" % m.to_pwm())
            tmp.flush()
            auc,mncp = self._roc_metrics(tmp.name, sample_fa, bg_fa, tmp2.name)
            bla = sorted(motifs, cmp=lambda x,y: cmp(mncp[x.id], mncp[y.id]))
            for m in bla:
                self.logger.debug("sorted: %s %s %s" % (str(m), mncp[m.id], auc[m.id]))

            self.logger.debug("end list")
            best_motif = sorted(motifs, cmp=lambda x,y: cmp(mncp[x.id], mncp[y.id]))[-1]
            old_id = best_motif.id
            best_motif.id = "GimmeMotifs_%d" % (i + 1)
            best_id[best_motif.id] = old_id.split("_")[0]
            num_cluster["%s_%s" % (best_motif.id, best_motif.to_consensus())] = len(singles)
            if imgdir:
                best_motif.to_img(os.path.join(imgdir, best_motif.id), format="PNG")
            out.write("%s\n" % best_motif.to_pwm())
            tmp.close()
            tmp2.close()
        out.close()
        return num_cluster, best_id

    def run_full_analysis(self, inputfile, user_params={}):
        """ Full analysis: from bed-file to motifs (including clustering, ROC-curves, location plots and html report) """
        self.logger.info("Starting full motif analysis")
        self.logger.info("Using temporary directory {0}".format(mytmpdir()))
    
        params = self.config.get_default_params()
        params.update(user_params)
        
        if params["torque"]:
            from gimmemotifs.prediction_torque import pp_predict_motifs, PredictionResult
            self.logger.info("Using torque")
        else:
            from gimmemotifs.prediction import pp_predict_motifs, PredictionResult
            self.logger.info("Using pp")

        self.params = params
        #self.weird = params["weird_option"]

        background = [x.strip() for x in params["background"].split(",")]
        
        self.logger.info("Parameters:")
        for param, value in params.items():
            self.logger.info("  %s: %s" % (param, value))

        # Checking input
        self.input_type = "BED"
        # If we can load it as fasta then it is a fasta, yeh?
        try:
            Fasta(inputfile)
            self.logger.info("Inputfile is a FASTA file")
            self.input_type = "FASTA"
        except:
            # Leave it to BED
            pass

        if self.input_type == "FASTA":
            for bg in background:
                if not bg in FA_VALID_BGS:
                    self.logger.info("Input type is FASTA, can't use background type '%s'" % bg)
            background = [bg for bg in background if bg in FA_VALID_BGS]
            
        elif self.input_type == "BED":
            # Does the index_dir exist?  #bed-specific
            index_dir = os.path.join(self.config.get_index_dir(), params["genome"])
            if not os.path.exists(index_dir):
                self.logger.error("No index found for genome %s! Has GimmeMotifs been configured correctly and is the genome indexed?" % params["genome"])
                sys.exit(1)

            # is it a valid bed-file etc.
            self._check_input(inputfile)    # bed-specific

            # Check for valid background
            for bg in background:
                if not bg in BED_VALID_BGS:
                    self.logger.info("Input type is BED, can't use background type '%s'" % bg)
            background = [bg for bg in background if bg in BED_VALID_BGS]
    
        if len(background) == 0:
            self.logger.error("No valid backgrounds specified!")
            sys.exit(1)

        self.max_time = None
        max_time = None
        # Maximum time?
        if params["max_time"]:
            try:
                max_time = float(params["max_time"])
            except:
                self.logger.info("Could not parse max_time value, setting to no limit")
                self.max_time = None

            if max_time > 0:
                self.logger.info("Time limit for motif prediction: %0.2f hours" % max_time)
                max_time = 3600 * max_time
                self.max_time = max_time
                self.logger.debug("Max_time in seconds %0.0f" % self.max_time)
            else:
                self.logger.info("Invalid time limit for motif prediction, setting to no limit")
                self.max_time = None
        else:
                self.logger.info("No time limit for motif prediction")
            
        if "random" in background:
            self.markov_model = params["markov_model"]

        # Create the necessary files for motif prediction and validation
        if self.input_type == "BED":
            self.prepare_input_bed(inputfile, params["genome"], params["width"], params["fraction"], params["abs_max"], params["use_strand"])
        
        
             # Create file for location plots
            index_dir = os.path.join(self.config.get_index_dir(), params["genome"])
            lwidth = int(params["lwidth"])
            width = int(params["width"])
            extend = (lwidth - width) / 2
            genome_index.track2fasta(index_dir, self.validation_bed, self.location_fa, extend_up=extend, extend_down=extend, use_strand=params["use_strand"])
        
        elif self.input_type == "FASTA":
            self.prepare_input_fa(inputfile, params["width"], params["fraction"], params["abs_max"])
        
            # File for location plots
            self.location_fa = self.validation_fa
            fa = Fasta(self.location_fa)
            seqs = fa.seqs
            lwidth = len(seqs[0]) 
            all_same_width = not(False in [len(seq) == lwidth for seq in seqs])
            if not all_same_width:
                self.logger.warn("PLEASE NOTE: FASTA file contains sequences of different lengths. Positional preference plots will be incorrect!")
        
        else:
            self.logger.error("Unknown input type, shouldn't happen")
            sys.exit(1)

        tools = dict([(x.strip(), x in [y.strip() for y in  params["tools"].split(",")]) for x in params["available_tools"].split(",")])
    
        self.create_background(background, params["genome"], params["width"])

        # Predict the motifs
        analysis = params["analysis"]
        if self.parallel:
            """ Predict motifs, input is a FASTA-file"""
            self.logger.info("Starting motif prediction (%s) using %s" % 
                (analysis, ", ".join([x for x in tools.keys() if tools[x]])))

            bg_file = self.bg_file["fa"][sorted(background, lambda x,y: cmp(BG_RANK[x], BG_RANK[y]))[0]]
            self.logger.info("Using bg_file %s for significance" % bg_file)
            result = pp_predict_motifs(self.prediction_fa, self.predicted_pfm, analysis, params["genome"], params["use_strand"], self.prediction_bg, tools, self.job_server(), logger=self.logger, max_time=self.max_time, fg_file=self.validation_fa, bg_file=bg_file)
    
            motifs = result.motifs
            self.logger.info("Predicted %s motifs, written to %s" % (len(motifs), self.predicted_pfm))

        
        if len(motifs) == 0:
            self.logger.info("No motifs found. Done.")
            sys.exit()
        
        # Write stats output to file
        f = open(self.stats_file, "w")
        stat_keys = result.stats.values()[0].keys()
        f.write("%s\t%s\n" % ("Motif", "\t".join(stat_keys)))
        for motif in motifs:
            stats = result.stats["%s_%s" % (motif.id, motif.to_consensus())]
            if stats:
                f.write("%s\t%s\n" % (motif.id, "\t".join([str(stats[k]) for k in stat_keys])))
            else:
                self.logger.error("No stats for motif {0}, skipping this motif!".format(motif.id))
                motifs.remove(motif)
        f.close()
    
        self.motifs_with_stats = motifs

        f = open(self.ranks_file, "w")
        tools = dict((m.id.split("_")[0],1) for m in motifs).keys()
        f.write("Metric\tType\t%s\n" % ("\t".join(tools)))
        for stat in ["mncp", "roc_auc", "maxenr"]:
            best_motif = {}
            for motif in self.motifs_with_stats:
                val = result.stats["%s_%s" % (motif.id, motif.to_consensus())][stat]
                name = motif.id.split("_")[0]
                if val > best_motif.setdefault(name, 0):
                    best_motif[name] = val
            names = best_motif.keys()
            vals = [best_motif[name] for name in names]
            rank = rankdata(vals)
            ind = [names.index(x) for x in tools]
            
            f.write("%s\t%s\t%s\n" % (stat, "value", "\t".join([str(vals[i]) for i in ind])))
            f.write("%s\t%s\t%s\n" % (stat, "rank", "\t".join([str(rank[i]) for i in ind])))
        f.close()
            
            
            #self.logger.debug("RANK: %s" % stat)
            #self.logger.debug("\t".join([str(x) for x in names]))
            #self.logger.debug("\t".join([str(x) for x in vals]))
            #self.logger.debug("\t".join([str(x) for x in rank]))

        # Determine significant motifs
        nsig = 0 
        f = open(self.significant_pfm, "w")
        for motif in motifs:
            stats = result.stats["%s_%s" % (motif.id, motif.to_consensus())]
            if stats["maxenr"] >= 3 and stats["roc_auc"] >= 0.55 and stats['enr_fdr'] >= 2:
                f.write("%s\n" % motif.to_pfm())
                nsig += 1
        f.close()        
        self.logger.info("%s motifs are significant, written to %s" % (nsig, self.significant_pfm))
        
        if nsig == 0:
            self.logger.info("No significant motifs found. Done.")
            sys.exit()
        
        # ROC metrics of significant motifs
        for bg in background:
            self._roc_metrics(self.significant_pfm, self.validation_fa, self.bg_file["fa"][bg], self.bg_file["roc"][bg])
        
        # Cluster significant motifs
        clusters = self._cluster_motifs(self.significant_pfm, self.cluster_pwm, self.outdir, params["cluster_threshold"])
        
        # Determine best motif in cluster
        num_cluster, best_id = self._determine_best_motif_in_cluster(clusters, self.final_pwm, self.validation_fa, bg_file, self.imgdir)
        
        ### Enable parallel and modular evaluation of results
        # Scan (multiple) files with motifs
        # Define callback functions once scanning is finished:
        #    - ROC plot
        #     - Statistics
        #    - Location plots (histogram)
        #     -
        
        # Stars
        tmp = NamedTemporaryFile(dir=mytmpdir()).name
        p = PredictionResult(tmp, logger=self.logger, job_server=self.server, fg_file = self.validation_fa, bg_file = bg_file) 
        p.add_motifs("Clustering",  (pwmfile_to_motifs(self.final_pwm), "",""))
        while len(p.stats.keys()) < len(p.motifs):
            sleep(5)

        for mid, num in num_cluster.items():
            p.stats[mid]["numcluster"] = num

        all_stats = {
            "mncp": [2, 5, 8],                
            "roc_auc": [0.6, 0.75, 0.9],    
            "maxenr": [10, 20, 30],         
            "enr_fdr": [4, 8, 12],         
            "fraction": [0.4, 0.6, 0.8],    
            "ks_sig": [4, 7, 10],
            "numcluster": [3, 6, 9],
        }

        
        # ROC plots
        for bg in background:
            self.create_roc_plots(self.final_pwm, self.validation_fa, self.bg_file["fa"][bg], bg)
        
        # Location plots
        self.logger.info("Creating localization plots")
        motifs = pwmfile_to_motifs(self.final_pwm)
        for motif in motifs:
            m = "%s_%s" % (motif.id, motif.to_consensus())
            s = p.stats[m]
            outfile = os.path.join(self.imgdir, "%s_histogram.svg" % motif.id)
            motif_localization(self.location_fa, motif, lwidth, outfile, cutoff=s["cutoff_fdr"])
    
            s["stars"] = int(mean([star(s[x], all_stats[x]) for x in all_stats.keys()]) + 0.5)
            self.logger.debug("Motif %s: %s stars" % (m, s["stars"]))

        # Calculate enrichment of final, clustered motifs
        self.calculate_cluster_enrichment(self.final_pwm, background)

        # Create report    
        self.print_params()
        self._calc_report_values(self.final_pwm, background)
        self._create_report(self.final_pwm, background, stats=p.stats, best_id=best_id)
        self._create_text_report(self.final_pwm, background)
        self.logger.info("Open %s in your browser to see your results." % (self.motif_report))
        
        if not(params["keep_intermediate"]):
            
            self.logger.info("Deleting intermediate files. Please specifify the -k option if you want to keep these files.")
            shutil.rmtree(self.tmpdir)

        self.logger.info("Done")


if __name__ == "__main__":
    gm = GimmeMotifs()
    gm.run_full_analysis(sys.argv[1])

