## $Id: Makefile.am 2599 2008-04-30 08:59:29Z tbailey $
##
## Process this file with automake to produce Makefile.in
##
## # $Log$
##

AUTOMAKE_OPTIONS = no-dependencies

EXAMPLES = \
  crp0.fasta \
  crp0.meme.xml \
  FimoClient.pl \
  FimoClient.py \
  MemeClient.pl \
  MemeClient.py

if WEBSITE
exdir = $(WEBDIR)/doc/examples/sample_opal_scripts
else
exdir = $(prefix)/doc/examples/sample_opal_scripts
endif

ex_DATA = $(EXAMPLES)


# If .svnignore file doesn't exist
# create an empty one
.svnignore:
	if [ -e .svn ] ; then touch .svnignore ; fi

# Update SVN svn:ignore property
# If .svnignore exists and longer then 0 bytes.
.svnignore.old:.svnignore
	if [ -e .svn ] ; \
  then \
    if [ -s .svnignore ] ; \
    then \
      svn propset svn:ignore -F .svnignore .  ; \
      cp .svnignore .svnignore.old; \
    fi \
  fi

EXTRA_DIST = $(EXAMPLES)
