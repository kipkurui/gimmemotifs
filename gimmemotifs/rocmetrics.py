# Copyright (c) 2009-2010 Simon van Heeringen <s.vanheeringen@ncmls.ru.nl>
#
# This module is free software. You can redistribute it and/or modify it under 
# the terms of the MIT License, see the file COPYING included with this 
# distribution.

""" Module to calculate ROC and MNCP scores """


# External imports
from scipy.stats import stats
from numpy import array

def fraction_fdr(fg_vals, bg_vals, fdr=5):
    from scipy.stats import scoreatpercentile
    fg_vals = array(fg_vals)
    s = scoreatpercentile(bg_vals, 100 - fdr)
    return len(fg_vals[fg_vals >= s]) / float(len(fg_vals))

def score_at_fdr(fg_vals, bg_vals, fdr=5):
    from scipy.stats import scoreatpercentile
    bg_vals = array(bg_vals)
    return scoreatpercentile(bg_vals, 100 - fdr)

def enr_at_fdr(fg_vals, bg_vals, fdr=5):
    from scipy.stats import scoreatpercentile
    pos = array(fg_vals)
    neg = array(bg_vals)
    s = scoreatpercentile(neg, 100 - fdr)
    return len(pos[pos >= s]) / float(len(neg[neg >= s])) * len(neg) / float(len(pos))

def max_enrichment(fg_vals, bg_vals, minbg=2):
    from numpy import hstack,argsort,ones,zeros

    scores = hstack((fg_vals, bg_vals))
    idx = argsort(scores)
    x = hstack((ones(len(fg_vals)), zeros(len(bg_vals))))
    xsort = x[idx]

    m = 0
    s = 0
    for i in range(len(scores), 0, -1):
        bgcount = float(len(xsort[i:][xsort[i:] == 0]))
        if bgcount >= minbg:
            enr = len(xsort[i:][xsort[i:] == 1]) / bgcount
            if enr > m:
                m = enr
                s = scores[idx[i]]
    return m, s

def MNCP(fg_vals, bg_vals):
    from scipy.stats import stats
    from numpy import mean,array,hstack
    #from pylab import *
    fg_len = len(fg_vals)
    total_len = len(fg_vals) + len(bg_vals)

    if type(fg_vals) != type(array([])):
        fg_vals = array(fg_vals)
    if type(bg_vals) != type(array([])):
        bg_vals = array(bg_vals)
    
    fg_rank = stats.rankdata(fg_vals)
    total_rank = stats.rankdata(hstack((fg_vals, bg_vals)))

    slopes = []
    for i in range(len(fg_vals)):
        slope = ((fg_len - fg_rank[i] + 1) / fg_len ) / ((total_len - total_rank[i] + 1)/ total_len)
        slopes.append(slope)
    return mean(slopes)

def ROC_AUC(fg_vals, bg_vals):
    from scipy.stats import stats
    from numpy import mean,array,hstack
    #if len(fg_vals) != len(bg_vals):
    #    return None
    
    if len(fg_vals) == 0 or len(bg_vals) == 0:
        return None
    
    fg_len = len(fg_vals)
    total_len = len(fg_vals) + len(bg_vals)
    
    if type(fg_vals) != type(array([])):
        fg_vals = array(fg_vals)
    if type(bg_vals) != type(array([])):
        bg_vals = array(bg_vals)

    fg_rank = stats.rankdata(fg_vals) 
    total_rank = stats.rankdata(hstack((fg_vals, bg_vals)))
    
    return (sum(total_rank[:fg_len]) - sum(fg_rank))/ (fg_len * (total_len - fg_len))

def ROC_AUC_xlim(x_bla, y_bla, xlim=None):
    x = x_bla[:]
    y = y_bla[:]

    x.sort()
    y.sort()

    u = {}
    for i in x + y:
        u[i] = 1

    vals = u.keys()
    vals.sort()
    
    len_x = float(len(x))
    len_y = float(len(y))
    
    new_x = []
    new_y = []
    
    x_p = 0
    y_p = 0
    for val in vals[::-1]:
        while len(x) > 0 and x[-1] >= val:
            x.pop()
            x_p += 1
        while len(y) > 0 and y[-1] >= val:
            y.pop()
            y_p += 1
        new_y.append((len_x - x_p) / len_x)
        new_x.append((len_y - y_p) / len_y)
    
    #print new_x
    #print new_y
    new_x = 1 - array(new_x)
    new_y = 1 - array(new_y)
    #plot(new_x, new_y)
    #show()

    x = new_x
    y = new_y

    if len(x) != len(y):
        raise "Unequal!"

    if not xlim:
        xlim = 1.0

    auc = 0.0
    bla = zip(stats.rankdata(x), range(len(x)))

    def sortfunc(x,y):
        res = x[0] - y[0]
        if res < 0:
            return -1
        elif res > 0:
            return 1
        elif res == 0:
            return y[1] - x[1]
    
    bla.sort(sortfunc)
    
    prev_x = x[bla[0][1]]
    prev_y = y[bla[0][1]]
    index = 1

    while index < len(bla) and x[bla[index][1]] <= xlim:

        (rank, i) = bla[index]
        
        auc += y[i] * (x[i] - prev_x) - ((x[i] - prev_x) * (y[i] - prev_y) / 2.0)
        prev_x = x[i]
        prev_y = y[i]
        index += 1
    
    if index < len(bla):
        (rank, i) = bla[index]
        auc += prev_y * (xlim - prev_x) + ((y[i] - prev_y)/(x[i] - prev_x) * (xlim -prev_x) * (xlim - prev_x)/2)

    return auc

def ROC_values(x_bla, y_bla):
    if len(x_bla) == 0 or len(y_bla) == 0:
        return [],[]

    x = x_bla[:]
    y = y_bla[:]

    x.sort()
    y.sort()

    u = {}
    for i in x + y:
        u[i] = 1

    vals = u.keys()
    vals.sort()
    
    len_x = float(len(x))
    len_y = float(len(y))
    
    new_x = []
    new_y = []
    
    x_p = 0
    y_p = 0
    for val in vals[::-1]:
        while len(x) > 0 and x[-1] >= val:
            x.pop()
            x_p += 1
        while len(y) > 0 and y[-1] >= val:
            y.pop()
            y_p += 1
        new_y.append((len_x - x_p) / len_x)
        new_x.append((len_y - y_p) / len_y)
    
    #print new_x
    #print new_y
    new_x = 1 - array(new_x)
    new_y = 1 - array(new_y)
    
    return (new_x, new_y)

def max_fmeasure(x,y):
    from numpy import array, logical_and, nanmax
    x = array(x[:])
    y = array(y[:])
    p = y / (y + x)
    filt = logical_and((p * y) > 0, (p + y) > 0)
    p = p[filt]
    y = y[filt]
    
    f = (2 * p * y) / (p + y)
    if len(f) > 0:
        return nanmax(f), nanmax(y[f == nanmax(f)])
    else:
        return None,None
