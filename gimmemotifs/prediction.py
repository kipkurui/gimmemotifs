# Copyright (c) 2009-2010 Simon van Heeringen <s.vanheeringen@ncmls.ru.nl>
#
# This module is free software. You can redistribute it and/or modify it under 
# the terms of the MIT License, see the file COPYING included with this 
# distribution.

""" Parallel prediction of sequence motifs """

# Python imports
import sys
import logging
import os
import subprocess 
import thread
from time import time
import inspect

# External imports
import pp

# GimmeMotifs imports
from gimmemotifs import tools as tool_classes
from gimmemotifs.comparison import *
from gimmemotifs.nmer_predict import *
from gimmemotifs.config import *
from gimmemotifs.fasta import *
from gimmemotifs import mytmpdir

class PredictionResult:
    def __init__(self, outfile, logger=None, fg_file=None, bg_file=None, job_server=None):
        self.lock = thread.allocate_lock()
        self.motifs = []
        self.finished = []
        self.logger = logger
        self.stats = {}
        self.outfile = outfile
        self.job_server = job_server

        if fg_file and bg_file:
            self.fg_fa = Fasta(fg_file)
            self.bg_fa = Fasta(bg_file)
            self.do_stats = True
        else:
            self.do_stats = False

    def add_motifs(self, job, args):
        # Callback function for motif programs
        motifs, stdout, stderr = args
        
        if self.logger:
            self.logger.info("%s finished, found %s motifs" % (job, len(motifs))) 
        
        for motif in motifs:
            self.lock.acquire()
            f = open(self.outfile, "a")
            f.write("%s\n" % motif.to_pfm())
            f.close()
            self.motifs.append(motif)
            if self.do_stats:
                self.logger.debug("Starting stats job of motif %s" % motif.id)
                self.job_server.submit(
                                    motif.stats, 
                                    (self.fg_fa, self.bg_fa), 
                                    (), 
                                    (),
                                    self.add_stats, 
                                    ("%s_%s" % (motif.id, motif.to_consensus()),), 
                                    group="stats"
                                    )
            self.lock.release()
        
        self.logger.debug("stdout %s: %s" % (job, stdout))
        self.logger.debug("stdout %s: %s" % (job, stderr))
        self.finished.append(job)

    def add_stats(self, motif, stats):
        self.logger.debug("Stats: %s %s" % (motif, stats))
        self.stats[motif] = stats

    def get_remaining_stats(self):
        for motif in self.motifs:
            n = "%s_%s" % (motif.id, motif.to_consensus())
            if not self.stats.has_key(n):
                self.logger.info("Adding %s again!" % n)
                self.job_server.submit(motif.stats, (self.fg_fa, self.bg_fa), (), (), self.add_stats, ("%s_%s" % (motif.id, motif.to_consensus()),), group="stats")

def pp_predict_motifs(fastafile, outfile, analysis="small", organism="hg18", single=False, background="", tools={}, job_server="", ncpus=8, logger=None, max_time=None, fg_file=None, bg_file=None):
    
    config = MotifConfig()

    if not tools:
        tools = dict([(x,1) for x in config.get_default_params["tools"].split(",")])
    
    if not logger:
        logger = logging.getLogger('prediction.pp_predict_motifs')

    wmin = 5 
    step = 1
    if analysis in ["large","xl"]:
        step = 2
        wmin = 6
    
    analysis_max = {"xs":5,"small":8, "medium":10,"large":14, "xl":20}
    wmax = analysis_max[analysis]

    if analysis == "xs":
        sys.stderr.write("Setting analysis xs to small")
        analysis = "small"

    if not job_server:
        job_server = pp.Server(ncpus, secret='pumpkinrisotto')
    
    jobs = {}
    
    result = PredictionResult(outfile, logger=logger, fg_file=fg_file, bg_file=bg_file, job_server=job_server)
    
    # Dynamically load all tools
    toolio = [x[1]() for x in inspect.getmembers(
                                                tool_classes, 
                                                lambda x: 
                                                        inspect.isclass(x) and 
                                                        issubclass(x, tool_classes.MotifProgram)
                                                ) if x[0] != 'MotifProgram']
    
    # TODO:
    # Add warnings for running time: Weeder, MoAn, GADEM
        
    ### Add all jobs to the job_server ###
    params = {'analysis': analysis, 'background':background, "single":single, "organism":organism}
    for t in toolio:
        if tools.has_key(t.name) and tools[t.name]:
            if t.use_width:
                for i in range(wmin, wmax + 1, step):
                    logger.debug("Starting %s job, width %s" % (t.name, i))
                    job_name = "%s_width_%s" % (t.name, i)
                    params['width'] = i
                    jobs[job_name] = job_server.submit(
                        t.run, 
                        (fastafile, ".", params, mytmpdir()), 
                        (tool_classes.MotifProgram,),
                        ("gimmemotifs.config",),  
                        result.add_motifs, 
                        (job_name,))
            else:
                logger.debug("Starting %s job" % t.name)
                job_name = t.name
                jobs[job_name] = job_server.submit(
                    t.run, 
                    (fastafile, ".", params, mytmpdir()), 
                    (tool_classes.MotifProgram,),
                    ("gimmemotifs.config",), 
                    result.add_motifs, 
                    (job_name,))
        else:
            logger.debug("Skipping %s" % t.name)
    
    ### Wait until all jobs are finished or the time runs out ###
    start_time = time()    
    try:
        # Run until all jobs are finished
        while len(result.finished) < len(jobs.keys()) and (not(max_time) or time() - start_time < max_time):
            pass
        if len(result.finished) < len(jobs.keys()):
            logger.info("Maximum allowed running time reached, destroying remaining jobs")
            job_server.destroy()
            result.get_remaining_stats()
    ### Or the user gets impatient... ###
    except KeyboardInterrupt, e:
        # Destroy all running jobs
        logger.info("Caught interrupt, destroying all running jobs")
        job_server.destroy()
        result.get_remaining_stats()
        
    # Wait for all stats jobs to finish
    job_server.wait(group="stats")    
    
    logger.info("Waiting for calculation of motif statistics to finish")
    while len(result.stats.keys()) < len(result.motifs):
        sleep(5)
    
    return result
