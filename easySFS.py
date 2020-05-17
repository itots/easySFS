#!/usr/bin/env python

'''
this script only retains bi-allelic SNPs.
'''
from __future__ import print_function
import matplotlib
matplotlib.use('PDF')
from collections import Counter
from collections import OrderedDict
from itertools import combinations
import pandas as pd
import numpy as np
import argparse
import shutil
import gzip
import copy
import dadi
import sys
import os

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def dadi_preview_projections(dd, pops, ploidy, fold):
    msg = """
    Running preview mode. We will print out the results for # of segregating sites
    for multiple values of projecting down for each population. The dadi
    manual recommends maximizing the # of seg sites for projections, but also
    a balance must be struck between # of seg sites and sample size.

    For each population you should choose the value of the projection that looks
    best and then rerun easySFS with the `--proj` flag.
    """
    print(msg)
    for pop in pops:
        print(pop)
        seg_sites = {}
        ## Calculate projections for up to 2 x the number of samples,
        ## so this is assuming populations are diploid.
        ## The +1 makes it possible to see preview including all samples per pop
        for x in range(2, ploidy*len(pops[pop])+1):
            fs =  dadi.Spectrum.from_data_dict(dd, [pop], [x], polarized=fold)
            s = fs.S()
            seg_sites[x] = round(s)
            print("({}, {})".format(x, round(s)), end="\t")
        print("")
        ## Old way that's a little uglier
        #for x in range(2,len(pops[pop])):
        #    print(seg_sites[x], end="\t")
        print("\n")


def dadi_oneD_sfs_per_pop(dd, pops, proj, unfold, outdir, prefix, dtype, bootstrap):
    dadi_dir = os.path.join(outdir, "dadi")
    fsc_dir = os.path.join(outdir, "fastsimcoal2")
    M_or_D = "D" if unfold else "M"
    for i, pop in enumerate(pops):
        if bootstrap is None:
            print("Doing 1D sfs - {}".format(pop))
        dadi_sfs_file = os.path.join(dadi_dir, pop+"-"+str(proj[i])+".sfs")

        fs = dadi.Spectrum.from_data_dict(dd, [pop], [proj[i]], mask_corners=True, polarized=unfold)

        ## Do int bins rather than float
        if dtype == "int":
            dat = np.rint(np.array(fs.data))
            fs = dadi.Spectrum(dat, data_folded=fs.folded, mask=fs.mask, fill_value=0, dtype=int)

        fs.to_file(dadi_sfs_file)

        ## Convert each 1D sfs to fsc format
        fsc_oneD_filename = os.path.join(fsc_dir, pop+"_{}AFpop0.obs".format(M_or_D))
        with open(fsc_oneD_filename, 'w') as outfile:
            outfile.write("1 observation\n")
            outfile.write("\t".join(["d0_"+str(x) for x in range(proj[i]+1)]) + "\n")
            ## Grab the fs data from the dadi sfs
            with open(dadi_sfs_file) as infile:
                outfile.write(infile.readlines()[1])
                outfile.write("\n")


def dadi_twoD_sfs_combinations(dd, pops, proj, unfold, outdir, prefix, dtype, verbose, bootstrap):
    dadi_dir = os.path.join(outdir, "dadi")
    fsc_dir = os.path.join(outdir, "fastsimcoal2")
    M_or_D = "D" if unfold else "M"
    ## All combinations of pairs of populations
    popPairs = list(combinations(pops, 2))
    ## All combinations of corresponding projection values
    ## This is hackish, it really relies on the fact that `combinations`
    ## is generating combinations in the same order for pops and projs
    projPairs = list(combinations(proj, 2))
    ## Make a dict for pop indices. this is a mapping of population labels
    ## to values (ie. {'pop1':1, 'pop2',2}) for labeling the fsc file names
    popidx = {}
    for i, pop in enumerate(pops):
        popidx[pop] = i
    if verbose: print("Population pairs - {}".format(popPairs))
    if verbose: print("Projections for each pop pair - {}".format(projPairs))
    for i, pair in enumerate(popPairs):
        if bootstrap is None:
            print("Doing 2D sfs - {}".format(pair))
        dadi_joint_filename = os.path.join(dadi_dir, "-".join(pair)+".sfs")
        fs = dadi.Spectrum.from_data_dict(dd, list(pair), list(projPairs[i]), polarized=unfold)

        ## Do int bins rather than float
        if dtype == "int":
            dat = np.rint(np.array(fs.data))
            fs = dadi.Spectrum(dat, data_folded=fs.folded, mask=fs.mask, fill_value=0, dtype=int)

        fs.to_file(dadi_joint_filename)

        ## Convert each 2D sfs to fsc format
        ## NB: FSC joint format file names look like this: <prefix>_jointMAFpop1_0.obs
        ## Where the first pop specified is listed in the rows and the second pop
        ## specified is listed in the columns.
        fsc_twoD_filename = os.path.join(fsc_dir, prefix+"_joint{}AFpop{}_{}.obs".format(M_or_D, popidx[pair[1]], popidx[pair[0]]))
        with open(fsc_twoD_filename, 'w') as outfile:
            outfile.write("1 observation\n")
            ## Format column headers (i.e. d0_0 d0_1 d0_2 .. d0_n for deme 0 up to sample size of n)
            outfile.write("\t" + "\t".join(["d{}_".format(popidx[pair[0]]) + str(x) for x in range(projPairs[i][0]+1)]) + "\n") 

            ## Format row headers
            row_headers = ["d{}_".format(popidx[pair[1]]) + str(x) for x in range(projPairs[i][1]+1)]
            ## Read in the joint fs from dadi and format it nice for fsc
            with open(dadi_joint_filename) as infile:
                ## Get the second line of the dadi-style sfs which contains the data
                row_data = infile.readlines()[1].split()
                ## The length of each row is determined by the number of columns which == the size of the projection for pop2
                ## Have to add 1 to the value of the projection because range stops after 'n' elements
                ## but we want all n+1 elements from 0,1,2,..,n
                row_size = projPairs[i][0] + 1
                ## Slice the row data into evenly sized chunks based on the number of columns
                rows = [row_data[i:i + row_size] for i in range(0, len(row_data), row_size)]
                ## Sanity check. Make sure the number of rows you got is the same number you're expecting
                ## to get (# rows should == size of pop0 projection)
                if not len(row_headers) == len(rows):
                    print("FSC Joint SFS failed for - {}".format(pair))
                    print("Row headers - {}".format(row_headers))
                    print("Row data - {}".format(rows))
                    print("Len header / data\n{}\t{}".format(len(row_headers), len(rows)))
                    return
                else:
                    pass
                ## Write out each row to the file
                for i, row_head in enumerate(row_headers):
                    outfile.write(row_head + "\t" + " ".join(rows[i]) + "\n")


def dadi_multiSFS(dd, pops, proj, unfold, outdir, prefix, dtype, bootstrap):
    if bootstrap is None:
        print("Doing multiSFS for all pops")
    dadi_dir = os.path.join(outdir, "dadi")
    fsc_dir = os.path.join(outdir, "fastsimcoal2")
    dadi_multi_filename = os.path.join(dadi_dir, "-".join(pops)+".sfs")

    ## Get the multiSFS
    fs = dadi.Spectrum.from_data_dict(dd, pops, proj, polarized=unfold)

    ## Do int bins rather than float
    if dtype == "int":
        dat = np.rint(np.array(fs.data))
        fs = dadi.Spectrum(dat, data_folded=fs.folded, mask=fs.mask, fill_value=0, dtype=int)

    ## Write out the dadi file
    fs.to_file(dadi_multi_filename)
    
    ## Convert to fsc multiSFS format
    fsc_multi_filename = os.path.join(fsc_dir, prefix + "_MSFS.obs")
    with open(fsc_multi_filename, 'w') as outfile:
        outfile.write("1 observations. No. of demes and sample sizes are on next line.\n")
        outfile.write(str(len(pops)) + "\t" + " ".join([str(x) for x in proj]) + "\n") 
        with open(dadi_multi_filename) as infile:
            outfile.write(infile.readlines()[1])
            outfile.write("\n")
    return dadi_multi_filename


def dadi_to_momi(infile, outdir=None, verbose=False):
    try:
        import momi
    except:
        if verbose: print("Install momi to get momi-style sfs conversion as well.")
        return
    if not outdir == None:
        momi_dir = os.path.join(outdir, "momi")
        if not os.path.exists(momi_dir):
            os.mkdir(momi_dir)
        outfile = infile.split(".sfs")[0] + "_momi.sfs"
        outfile = os.path.join(outdir, outfile.split("/")[-1])
    else:
        outfile = infile + "_momi.sfs"

    dat = open(infile).readlines()
    ## Get rid of comment lines
    dat = [x.strip() for x in dat if not x.startswith("#")]
    if not len(dat) == 3:
        raise Exception("Malformed dadi sfs {}.\n  Must have 3 lines, yours has {}".format(infile, len(dat)))

    ## Parse the info line into nsamps per pop (list of ints), folding flag, and pop names list (if they are given)
    info = dat[0].split()
    nsamps = []
    ## Keep carving off values as long as they cast successfully as int
    for i in info:
        try:
            nsamps.append(int(i))
        except:
            pass
    nsamps = np.array(nsamps)
    pops = [x.replace('"', '') for x in info[len(nsamps)+1:]]
    folded = info[len(nsamps)]
    folded = False if "un" in folded else True
    if not len(pops) == len(nsamps):
        print("Number of populations doesn't agree with number of pop names, using generic names.")
        pops = ["pop"+x for x in range(len(nsamps))]
    if verbose: print("Info nsamps={} folded={} pops={}".format(nsamps, folded, pops))

    ## Get mask
    mask = list(map(int, dat[2].split()))
    if verbose: print(mask)

    ## Get sfs, and reshape based on sample sizes
    sfs = list(map(float, dat[1].split()))
    if verbose: print(sfs)
    length = np.ma.array(sfs, mask=mask).sum()
    sfs = np.array(sfs).reshape(nsamps)
    if verbose: print("length {}".format(length))
    if verbose: print(sfs)

    ## Get counts per sfs bin
    counts = Counter()
    for sfsbin in product(*[range(y) for y in [x for x in nsamps]]):
        ## Ignore monomorphic snps
        ## nsamps minus 1 here because of the off by one diff between number
        ## of bins in the sfs and actual number of samples
        if sfsbin == tuple(nsamps-1) or sfsbin == tuple([0] * len(nsamps)):
            continue
        ## ignore zero bin counts
        if sfs[sfsbin] == 0:
            continue
        if verbose: print(sfsbin, sfs[sfsbin]),
        counts.update({sfsbin:sfs[sfsbin]})
    if verbose: print("nbins {}".format(len(counts)))

    ## Convert SFS bin style into momi config style
    configs = pd.DataFrame(index=range(len(counts)), columns=pops)
 
    locus_info = []
    for i, c in enumerate(counts):
        ## (n-1) here because nbins in dadi sfs is n+1
        cfg = np.array([[(n-1)-x, x] for x,n in zip(c, nsamps)])
        configs.iloc[i] = [list(map(int, list(x))) for x in cfg]
        locus_info.append([0, i, counts[c]])
    if verbose: print("n_snps {}".format(np.sum([x[2] for x in locus_info])))

    ## Finally build the momi style sfs dictionary and write it out
    momi_sfs = {"sampled_pops":pops,
        "folded":folded,
        "length":int(length),
        "configs":configs.values.tolist(),
        "(locus,config_id,count)":locus_info}

    with open(outfile, 'w') as out:
        out.write("{}".format(json.dumps(momi_sfs)))
    ## make it pretty
    sfs = momi.Sfs.load(outfile)
    ## Fold if unfolded
    if folded: sfs = sfs.fold()
    sfs.dump(outfile)


def oneD_sfs_per_pop(dd, pops, outdir, prefix):
    for pop in pops:
        allele_counts = [dd[x]["calls"][pop] for x in dd.keys()]
#        print(allele_counts)        
        counts = Counter([x[1] for x in allele_counts])
        print(pop, counts)
        counts = Counter([x[0] for x in allele_counts])
        print(pop, counts)


def make_datadict(genotypes, pops, verbose=False, ploidy=1):
    dd = {}

    ## Get genotype counts for each population
    for (i, row) in enumerate(genotypes.iterrows()):  # Avoid duplicate rows removal in bootstrap data
        ## iterrows() returns a tuple for some reason
        row = row[1]

        calls = {}
        for pop in pops.keys():
            ## If there is a bunch of info associated w/ each snp then
            ## just carve it off for now.
            pop_genotypes = [row[x].split(":")[0] for x in pops[pop]]
            ref_count = sum([x == "0" or x == "0/0" or x == "0|0" for x in pop_genotypes]) * ploidy
            alt_count = sum([x == "1" or x == "1/1" or x == "1|1" for x in pop_genotypes]) * ploidy
            ## Haploids shouldn't have hets in the vcf 
            het_count = sum([x == "1/0" or x == "0/1" or x == "1|0" or x == "0|1" for x in pop_genotypes])

            ref_count += het_count
            alt_count += het_count
            calls[pop] = (ref_count, alt_count)

        dd[row["#CHROM"]+"-"+row["POS"]+"-"+str(i)] =\
            {"segregating":[row["REF"], row["ALT"]],\
            "calls":calls,\
            "outgroup_allele":row["REF"]}
    return dd


def read_input(vcf_name, all_snps=False, verbose=False):

    ## Counter to track which locus we're evaluating and a list
    ## to hold all lines for each locus so we can randomly
    ## select one snp per locus if necessary
    cur_loc_number = -1
    cur_loc_snps = []

    ## use gzip? 
    read_mode = 'r'
    if vcf_name.endswith(".gz"):
        read_mode = 'rt'
        ofunc = gzip.open
    else:  
        ofunc = open
    infile = ofunc(vcf_name, read_mode)
    lines = infile.readlines()
    infile.close()

    for line in lines:
        if line.startswith("#CHROM"):
            header = line

    ## Just get the data lines, not the comments
    lines = [x for x in lines if not x.startswith('#')]
    if verbose:
        print("  Number of snps in input file: {}".format(len(lines)))

    ## Randomly select one snp per locus
    if not all_snps:
        print("  Sampling one snp per locus")
        loci_nums = set([x.split()[0] for x in lines])
        loc_dict = {}
        for loc in loci_nums:
            loc_dict[loc] = []

        ## populate the loci dict
        for line in lines:
            loc_dict[line.split()[0]].append(line)

        lines = []
        for loc in loc_dict.values():
            line = np.random.choice(loc, 1)[0]
            lines.append(line)

        ## Sanity check.
        ## Some snp calling pipelines use the vcf Chrom/pos information to
        ## convey read/snp info per locus (ipyrad), some just assign
        ## all snps to one chrom and use pos/ID (tassel).
        ## If the user chooses to randomly sample one snp per block and the
        ## VCF doesn't use Chrom to indicate RAD loci then it'll just
        ## sample one snp for the whole dataset.
        if len(loc_dict) == 1:
            msg = """
    VCF file uses non-standard Chrom/pos information.
    We assume that Chrom indicates RAD loci and pos indicates snps within each locus 
    The VCF file passed does not have rad locus info in the Chrom field.

    You can re-run the easySFS conversion with the `-a` flag to use all snps in the conversion."""
            sys.exit(msg)

        if verbose:
            print("  Using n independent snps: {}".format(len(lines)))


    ## lines now here has a list of either all snps in the input
    ## or a subset that includes only one snp per locus
    genotypes = pd.DataFrame([x.split() for x in lines], columns=header.split())
    return genotypes


def get_inds_from_input(vcf_name, verbose):
    # Read in the vcf file and grab the line with the individual names
    # Add the 'U' to handle opening files in universal mode, squashes the
    # windows/mac/linux newline issue.
    ## use gzip? 
    indnames = []
    read_mode = 'r'
    if vcf_name.endswith(".gz"):
        read_mode = 'rt'
        ofunc = gzip.open
    else:  
        ofunc = open
    try:
        with ofunc(vcf_name, read_mode) as infile:
            for line in infile:
                if line.startswith('#'):
                    if line.startswith('#CHROM'):
                        row = line.strip().split()
                        # VCF file format spec says that if the file contains genotype
                        # data then "FORMAT" will be the last column header before
                        # sample IDs start
                        startcol = row.index('FORMAT')
                        indnames = [x for x in row[startcol+1:]]
                    else:
                        pass
                else:
                    break
    except Exception as inst:
        msg = """
    Problem reading individuals from input VCF file."""
        print("Error - {}".format(inst))
        raise

    if not indnames:
        raise Exception("No sample names found in the input vcf. Check vcf file formatting.")
    return indnames

    
def check_inputs(ind2pop, indnames, pops):
    ## Make sure all samples are present in both pops file and VCF, give the user the option
    ## to bail out if something is goofy
    pop_set = set(ind2pop.keys())
    vcf_set = set(indnames)
    
    if not pop_set == vcf_set:
        print("\nSamples in pops file not present in VCF: {}"\
            .format(", ".join(pop_set.difference(vcf_set))))
        ## Remove the offending samples from ind2pop
        map(ind2pop.pop, pop_set.difference(vcf_set))
        print("Samples in VCF not present in pops file: {}"\
            .format(", ".join(vcf_set.difference(pop_set))))

        ## Remove the offending individuals from the pops dict
        for k,v in pops.items():
            for ind in pop_set.difference(vcf_set):
                if ind in v:
                    v.remove(ind)
                    pops[k] = v
        ## Make sure to remove any populations that no longer have samples
        for k, v in pops.items():
            if not v:
                print("Empty population, removing - {}".format(k))
                pops.pop(k)

        cont = input("\nContinue, excluding samples not in both pops file and VCF? (yes/no)\n")  # Python 3 uses input not raw_input
        while not cont in ["yes", "no"]:
            cont = input("\nContinue, excluding samples not in both pops file and VCF? (yes/no)\n")  # Python 3 uses input not raw_input
        if cont == "no":
            sys.exit()
    return ind2pop, indnames, pops


def get_populations(pops_file, verbose=False):
    # Here we need to read in the individual population
    # assignments file and do this:
    # - populate the locs dictionary with each incoming population name
    # - populate another dictionary with individuals assigned to populations
    # Add the 'U' to handle opening files in universal mode, squashes the
    # windows/mac/linux newline issue.

    try:
        with open(pops_file, 'r') as popsfile:
            ind2pop = {}
            pops = OrderedDict()
        
            lines = popsfile.readlines()
            ## Get all the populations
            for line in lines:
                pops.setdefault(line.split()[1], [])
        
            for line in lines:
                ind = line.split()[0]
                pop = line.split()[1]
                ind2pop[ind] = pop
                pops[pop].append(ind)

        print("Processing {} populations - {}".format(len( pops ), pops.keys()))
        if(verbose):
            for pop,ls in pops.items():
                print(pop, ls)

    except Exception as inst:
        msg = """
    Problem reading populations file. The file should be plain text with one
    individual name and one population name per line, separated by any amount of
    white space. There should be no header line in this file. 
    An example looks like this:

        ind1    pop1
        ind2    pop1
        ind3    pop2
        ind4    pop2"""
        print(msg)
        print("    File you specified is: ".format(pops_file))
        print("    Error - {}".format(inst))
        raise

    return ind2pop, pops


def parse_command_line():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\n
    """)

    parser.add_argument("-a", dest="all_snps", action='store_true', 
        help="Keep all snps within each RAD locus (ie. do _not_ randomly sample 1 snp per locus).")

    parser.add_argument("-i", dest="vcf_name", required=True, 
        help="name of the VCF input file being converted")

    parser.add_argument("-p", dest="populations", required=True, 
        help="Input file containing population assignments per individual")

    parser.add_argument("--proj", dest="projections", 
        help="List of values for projecting populations down to different sample sizes")

    parser.add_argument("--preview", dest="preview", action='store_true',
        help="Preview the number of segragating sites per population for different projection values.")

    parser.add_argument("-o", dest="outdir", default='output', 
        help="Directory to write output SFS to")

    parser.add_argument("--ploidy", dest="ploidy", type=int, default=2,
        help="Specify ploidy. Default is 2. Only other option is 1 for haploid.")

    parser.add_argument("--prefix", dest="prefix", 
        help="Prefix for all output SFS files names.")

    parser.add_argument("--unfolded", dest="unfolded", action='store_true', 
        help="Generate unfolded SFS. This assumes that your vcf file is accurately polarized.")

    parser.add_argument("--dtype", dest="dtype", default="float",
        help="Data type for use in output sfs. Options are `int` and `float`. Default is `float`.")

    parser.add_argument("--GQ", dest="GQual", 
        help="minimum genotype quality tolerated", default=20)

    parser.add_argument("-f", dest="force", action='store_true',
        help="Force overwriting directories and existing files.")

    parser.add_argument("-v", dest="verbose", action='store_true',
        help="Set verbosity. Dump tons of info to the screen")

    parser.add_argument("-b", dest="bootstrap", type=int, default=None,
                        help="Perform bootstrap resampling. Specify # of samples.")

    parser.add_argument("-s", dest="seed", type=int, default=None,
                        help="Seed for bootstrap resampling.")

    parser.add_argument("-k", dest="block_size", type=int, default=None,
                        help="Block size (# SNPs) for bootstrap resampling.")

    parser.add_argument("-t", dest="threads", type=int, default=None,
                        help="# of threads for parallel bootstrapping.")

    ## if no args then return help message
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    ## parse args
    args = parser.parse_args()
    return args


def init(args):
    ## Set up output directory and output prefix
    outdir = args.outdir
    if os.path.exists(outdir) and args.force == False:
        print("\nOutput directory exists. Use -f to override.\n")
        sys.exit()
    if os.path.exists(outdir):
        shutil.rmtree(outdir)
    os.mkdir(outdir)

    if not args.prefix:
        prefix = args.vcf_name.split('/')[-1].split('.')[0]
    else:
        prefix = args.prefix
    if args.verbose:
        print("Prefix - {}".format(prefix))

    return outdir, prefix


def create_sfs(outdir, prefix, genotypes, pops, args):
    ## Make sub-directories
    os.mkdir(os.path.join(outdir, "dadi"))
    os.mkdir(os.path.join(outdir, "fastsimcoal2"))

    ## Convert dataframe to dadi-style datadict
    dd = make_datadict(genotypes, pops=pops, ploidy=args.ploidy, verbose=args.verbose)
    with open(os.path.join(outdir, "datadict.txt"), 'w') as outfile:
        for x,y in dd.items():
            outfile.write(x+str(y)+"\n")

    ## Validate values passed in for projecting
    proj = [int(x) for x in args.projections.split(",")]
    if not len(pops) == len(proj):

        msg = "You must pass in the same number of values for projection as you have populations specified"
        msg += "\n\nN pops = {}\nN projections = {}\nProjections = {}".format(len(pops), len(proj), proj)
        sys.exit(msg)

    ## Create 1D sfs for each population
    dadi_oneD_sfs_per_pop(dd, pops, proj=proj, unfold=args.unfolded, outdir=outdir, prefix=prefix, dtype=args.dtype,
                          bootstrap=args.bootstrap)

    ## Create pairwise 2D sfs for each population
    dadi_twoD_sfs_combinations(dd, pops, proj=proj, unfold=args.unfolded,\
                            outdir=outdir, prefix=prefix, dtype=args.dtype, verbose=args.verbose,
                               bootstrap=args.bootstrap)

    ## Create the full multiSFS for all popuations combined
    sfs_file = dadi_multiSFS(dd, pops, proj=proj, unfold=args.unfolded, outdir=outdir, prefix=prefix, dtype=args.dtype,
                             bootstrap=args.bootstrap)

    try:
        import momi
        ## Create momi-style sfs
        dadi_to_momi(infile=sfs_file, outdir=outdir, verbose=args.verbose)
    except:
        ## Can't create momi file at this point because we're locked to python2
        ## because of dadi.
        pass


def bootstrap_resampling(rep, genotypes, block_index, outdir, prefix, pops, args):

    ## Seed was specified to guarantee reproducibility.
    if args.seed is not None:
        seed = args.seed + rep
    else:
        np.random.seed()
        seed = np.random.RandomState()

    ## Resampling for SNPs
    if args.block_size is None:
        resampled = genotypes.sample(frac=1, replace=True, random_state=seed)
    ## Resampling for non-overlapping blocks (Block bootstrapping)
    else:
        resampled_index = genotypes.assign(block_index=block_index)[["#CHROM", "block_index"]].\
            drop_duplicates().sample(frac=1, replace=True, random_state=seed)
        resampled = genotypes.assign(block_index=block_index).\
            merge(resampled_index, how="inner", on=["#CHROM", "block_index"]).drop(columns="block_index")

    os.mkdir(os.path.join(outdir, "bootrep" + str(rep)))
    create_sfs(os.path.join(outdir, "bootrep" + str(rep)), prefix, resampled, pops, args)


def main():
    args = parse_command_line()

    if args.verbose:
        print("Input Arguments:\n\t{}".format(args))

    ## Set up output directory and output prefix
    if args.preview:
        if args.verbose: print("Doing preview so skipping directory initialization")
    else:
        outdir, prefix = init(args)

    ## Get populations and populations assignments for individuals
    ## ind2pop - a dictionary mapping individuals to populations
    ## pops - a dictionary of populations and all inds w/in them
    ind2pop, pops = get_populations(args.populations, args.verbose)

    ## Read in the names of individuals present in the vcf file
    indnames = get_inds_from_input(args.vcf_name, args.verbose)

    ## Check whether inds exist in the population mapping and input vcf
    ## files. Give the user an opportunity to bail if there is a mismatch.
    if not args.force:
        ind2pop, indnames, pops = check_inputs(ind2pop, indnames, pops)

    ## Reads the vcf and returns a pandas dataframe
    genotypes = read_input(args.vcf_name, all_snps=args.all_snps,
                            verbose=args.verbose)

    ## Convert dataframe to dadi-style datadict
    dd = make_datadict(genotypes, pops=pops, ploidy=args.ploidy, verbose=args.verbose)

    ## Do preview of various projections to determine good values
    if args.preview:
        dadi_preview_projections(dd, pops, ploidy=args.ploidy, fold=args.unfolded)
        sys.exit()

    elif args.projections:
        ## Validate values passed in for projecting
        proj = [int(x) for x in args.projections.split(",")]
        if not len(pops) == len(proj):

            msg = "You must pass in the same number of values for projection as you have populations specified"
            msg += "\n\nN pops = {}\nN projections = {}\nProjections = {}".format(len(pops), len(proj), proj)
            sys.exit(msg)

        ## Bootstrap resampling
        if args.bootstrap is not None:
            print("Start bootstrap resmpling")
            os.mkdir(os.path.join(outdir, "original"))
            create_sfs(os.path.join(outdir, "original"), prefix, genotypes, pops, args)

            if args.block_size is None:
                print("Resampling SNPs")
                block_index = None
            elif args.block_size < 0:
                msg = "Block size (-k) must be specified as positive value."
                sys.exit(msg)
            else:
                print("Resampling non-overlapping blocks (block bootstrapping)")
                ## Assign block index
                chrom_pos = genotypes.loc[:, ("#CHROM", "POS")].copy()
                chrom_pos.POS = chrom_pos.POS.astype(int)  # Change type for block indexing
                if len(set(chrom_pos["#CHROM"])) == 1:
                    chrom_pos["block_index"] = [i for i in range(len(chrom_pos) // args.block_size) for _ in range(args.block_size)] + \
                                               [len(chrom_pos) // args.block_size] * (len(chrom_pos) % args.block_size)
                ## Block is set separately for each chromosome
                else:
                    chrom_pos["block_index"] = chrom_pos.iloc[:, :2].groupby("#CHROM").transform(
                            lambda x: [i for i in range(x.shape[0] // args.block_size) for _ in range(args.block_size)] +
                                      [x.shape[0] // args.block_size] * (x.shape[0] % args.block_size))
                print("  Number of chromosomes: " + str(len(set(chrom_pos["#CHROM"]))))
                print("  Number of blocks: " + str(chrom_pos[["#CHROM", "block_index"]].drop_duplicates().shape[0]))
                print("  Block size (# SNPs): " + str(args.block_size))
                block_index = chrom_pos["block_index"]

            ## Parallelize bootstrap resampling
            if args.threads is not None:
                print("Bootstrapping in parallel...")
                from joblib import Parallel, delayed
                Parallel(n_jobs=-1, verbose=5)([
                    delayed(bootstrap_resampling)(rep=i, genotypes=genotypes, block_index=block_index,
                                                  outdir=outdir, prefix=prefix, pops=pops, args=args)
                    for i in range(args.bootstrap)])
            else:
                print("Bootstrapping serially...")
                for i in range(args.bootstrap):
                    print("# bootrep " + str(i))
                    bootstrap_resampling(rep=i, genotypes=genotypes, block_index=block_index,
                                         outdir=outdir, prefix=prefix, pops=pops, args=args)
            print("Done.")

        ## Original data
        else:
            create_sfs(outdir, prefix, genotypes, pops, args)

    else:
        print("Either --preview or --proj must be specified.")


if __name__ == "__main__":
    main()

