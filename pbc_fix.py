#generic python modules
import argparse
import operator
from operator import itemgetter
import sys, os, shutil
import os.path

################################################################################################################################################
# RETRIEVE USER INPUTS
################################################################################################################################################

#=========================================================================================
# create parser
#=========================================================================================
version_nb = "0.0.1"
parser = argparse.ArgumentParser(prog='pbc_fix', usage='', add_help=False, formatter_class=argparse.RawDescriptionHelpFormatter, description=\
'''
**********************************************
v''' + version_nb + '''
author: Jean Helie (jean.helie@bioch.ox.ac.uk)
git: https://github.com/jhelie/pbc_fix
**********************************************
	
[ DESCRITPION ]

This script updates atoms coordinates in case the system simulated expand or deforms
so that it crosses the boundaries of the unit cell. The script works by calculating
the minimum box size to contain the system for each frame and putting the system
whole back into this new box.

It works on either a gro file or a xtc trajectory but at the moment only rectangular
boxes and deformation along the z axis are dealt with.


[ NOTES ]

1. The script works by comparing each frame to the previous one therefore the
   xtc frames/gro files must be sufficiently closely related with respect to the z
   coordinate.

2. In case a xtc file is provided the coordinates of the first frame of the xtc (or 
   of the frame corresponding to -b) are used as intial reference. In this case the
   reference gro file is only used to define the sytem's topology.

3. The gro file via the -f flag provided is used for reference only - as an example
   of what the system looks like before pbc along z becomes an issue. In case an
   xtc file is provided it is NOT appended to the new xtc file.

4. Waters and ions are NOT dealt with so it's a good idea to pre-process the xtc
   file to remove them as it will load much faster.

5. In the output file coordinates are translated so that they are all positive. The
   buffer space to maintain along z between the lowest and highest particle can be
   specified via the --buffer option, so that the minimum distance between particles
   at the bottom and the top of the box will always be > buffer, even with pbc.


[ USAGE ]

Option	      Default  	Description                    
-----------------------------------------------------
-f			: reference coordinate file [.gro] (required)
-g			: coordinate file to fix [.gro]
-x			: trajectory file to fix [.xtc]
-o			: name of output folder
-b			: beginning time (ns) to process the xtc (optional)
-e			: ending time (ns) to process the xtc (optional)
-t 		[10]	: process every t-frames
--last			: only output last frame of xtc (useful as a later starting point if space limited) [TO DO]

Solvent selection
-----------------------------------------------------
--ions		['ION']	: residue name of ions
--water		['W']	: residue name of waters

Coordinates modification parameters
-----------------------------------------------------
--buffer	[80]	: z buffer to maintain (Angstrom) , see note 5
--delta 	[50]	: max z delta allowed between 2 frames (in % of box size) before considering a pbc jump
  
''')

#data options
parser.add_argument('-f', nargs=1, dest='reffilename', default=['no'], help=argparse.SUPPRESS, required=True)
parser.add_argument('-g', nargs=1, dest='grofilename', default=['no'], help=argparse.SUPPRESS)
parser.add_argument('-x', nargs=1, dest='xtcfilename', default=['no'], help=argparse.SUPPRESS)
parser.add_argument('-o', nargs=1, dest='output_folder', default=['pbc_fix'], help=argparse.SUPPRESS)
parser.add_argument('-b', nargs=1, dest='t_start', default=[-1], type=int, help=argparse.SUPPRESS)
parser.add_argument('-e', nargs=1, dest='t_end', default=[-1], type=int, help=argparse.SUPPRESS)
parser.add_argument('-t', nargs=1, dest='frames_dt', default=[10], type=int, help=argparse.SUPPRESS)
parser.add_argument('--last', dest='xtc_last', action='store_true', help=argparse.SUPPRESS)

#solvent selection
parser.add_argument('--ions', nargs=1, dest='ions', default=['ION'], help=argparse.SUPPRESS)
parser.add_argument('--water', nargs=1, dest='waters', default=['W'], help=argparse.SUPPRESS)

#coordinates modification parameters
parser.add_argument('--delta', nargs=1, dest='z_ratio', default=[50], type=float, help=argparse.SUPPRESS)
parser.add_argument('--buffer', nargs=1, dest='z_buffer', default=[80], type=float, help=argparse.SUPPRESS)

#other options
parser.add_argument('--version', action='version', version='%(prog)s v' + version_nb, help=argparse.SUPPRESS)
parser.add_argument('-h','--help', action='help', help=argparse.SUPPRESS)

#=========================================================================================
# store inputs
#=========================================================================================

#parse user inputs
#-----------------
args = parser.parse_args()
#data options
args.reffilename = args.reffilename[0]
args.grofilename = args.grofilename[0]
args.xtcfilename = args.xtcfilename[0]
args.output_folder = args.output_folder[0]
args.t_start=args.t_start[0]
args.t_end=args.t_end[0]
args.frames_dt=args.frames_dt[0]
#solvent selection
args.ions = args.ions[0]
args.waters = args.waters[0]
#coordinates modification parameters
args.z_ratio = args.z_ratio[0]/float(100)
args.z_buffer = args.z_buffer[0]

#create output file name
#-----------------------
global output_filename
if args.xtcfilename == 'no':
	output_filename = args.grofilename[:-4] + "_fixed.gro"
else:
	output_filename = args.xtcfilename[:-4] + "_fixed_t" + str(args.frames_dt) + ".xtc"

#=========================================================================================
# import modules (doing it now otherwise might crash before we can display the help menu!)
#=========================================================================================
#generic science modules
try:
	import math
except:
	print "Error: you need to install the maths module."
	sys.exit(1)
try:
	import numpy as np
except:
	print "Error: you need to install the np module."
	sys.exit(1)
try:
	import scipy
except:
	print "Error: you need to install the scipy module."
	sys.exit(1)
try:
	import matplotlib as mpl
	mpl.use('Agg')
	import matplotlib.colors as mcolors
	mcolorconv = mcolors.ColorConverter()
	import matplotlib.cm as cm				#colours library
	import matplotlib.ticker
	from matplotlib.ticker import MaxNLocator
	from matplotlib.font_manager import FontProperties
	fontP=FontProperties()
except:
	print "Error: you need to install the matplotlib module."
	sys.exit(1)
try:
	import pylab as plt
except:
	print "Error: you need to install the pylab module."
	sys.exit(1)

#MDAnalysis module
try:
	import MDAnalysis
	from MDAnalysis import *
	import MDAnalysis.selections
	import MDAnalysis.analysis
	import MDAnalysis.analysis.leaflet
	import MDAnalysis.analysis.distances
	#set MDAnalysis to use periodic boundary conditions
	MDAnalysis.core.flags['use_periodic_selections'] = True
	MDAnalysis.core.flags['use_KDTree_routines'] = False
except:
	print "Error: you need to install the MDAnalysis module first. See http://mdanalysis.googlecode.com"
	sys.exit(1)
	
#=========================================================================================
# sanity check
#=========================================================================================

if not os.path.isfile(args.reffilename):
	print "Error: file " + str(args.reffilename) + " not found."
	sys.exit(1)
if args.grofilename == 'no' and args.xtcfilename == 'no':
	print "Error: you need to specify a file to fix, either via -g or -x. See pbc_fix --help."
	sys.exit(1)
if args.grofilename != 'no' and not os.path.isfile(args.grofilename):
	print "Error: file " + str(args.grofilename) + " not found."
	sys.exit(1)
if args.xtcfilename != 'no' and not os.path.isfile(args.xtcfilename):
	print "Error: file " + str(args.xtcfilename) + " not found."
	sys.exit(1)
if args.z_buffer < 0:
	print "Error: the argument of --buffer should be positive. See pbc_fix --help."
	sys.exit(1)
if args.z_ratio < 0 or args.z_ratio > 100:
	print "Error: the argument of --delta should be a percentage between 0 and 100. See pbc_fix --help."
	sys.exit(1)

#=========================================================================================
# create folders and log file
#=========================================================================================

if os.path.isdir(args.output_folder):
	print "Error: folder " + str(args.output_folder) + " already exists, choose a different output name via -o."
	sys.exit(1)
else:
	#create folders
	os.mkdir(args.output_folder)

	#create log
	filename_log=os.getcwd() + '/' + str(args.output_folder) + '/pbc_fix.log'
	output_log=open(filename_log, 'w')		
	output_log.write("[pbc_fix v" + str(version_nb) + "]\n")
	output_log.write("\nThis folder and its content were created using the following command:\n\n")
	tmp_log="python pbc_fix.py"
	for c in sys.argv[1:]:
		tmp_log+=" " + c
	output_log.write(tmp_log + "\n")
	output_log.close()

	#copy input files
	shutil.copy2(args.reffilename, args.output_folder + "/")	


##########################################################################################
# FUNCTIONS DEFINITIONS
##########################################################################################

#=========================================================================================
# data loading
#=========================================================================================

def load_MDA_universe():
	
	#case: gro file only
	#-------------------
	if args.grofilename != "no":
		print "Loading reference structure..."
		U_ref=Universe(reffilename)
		print "Loading structure to fix..."
		U_new=Universe(grofilename)
		sele_ref=U_ref.selectAtoms("not resname W and not resname ION")
		sele_new=U_new.selectAtoms("not resname W and not resname ION")
	
	#case: xtc file
	#--------------
	else:
		global U
		global all_atoms
		global nb_atoms
		global nb_frames_xtc
		global frames_to_process
		global nb_frames_to_process
		global f_start
		global f_end	
		global z_coord_previous
		f_start = 0

		print "\nLoading trajectory..."
		U = Universe(args.reffilename, args.xtcfilename)
		U_timestep = U.trajectory.dt
		all_atoms = U.selectAtoms("not resname " + str(args.waters) + " and not resname " + str(args.ions))
		nb_atoms = all_atoms.numberOfAtoms()
		nb_frames_xtc = U.trajectory.numframes		
		#sanity check
		if U.trajectory[nb_frames_xtc-1].time/float(1000) < args.t_start:
			print "Error: the trajectory duration (" + str(U.trajectory.time/float(1000)) + "ns) is shorted than the starting stime specified (" + str(args.t_start) + "ns)."
			sys.exit(1)
		if nb_frames_xtc < args.frames_dt:
			print "Warning: the trajectory contains fewer frames (" + str(nb_frames_xtc) + ") than the frame step specified (" + str(args.frames_dt) + ")."

		#rewind trajectory
		U.trajectory.rewind()

		#create list of index of frames to process
		if args.t_end != -1:
			f_end = int((args.t_end*1000 - U.trajectory[0].time) / float(U_timestep))
			if f_end < 0:
				print "Error: the starting time specified is before the beginning of the xtc."
				sys.exit(1)
		else:
			f_end = nb_frames_xtc - 1		
		if args.t_start != -1:
			f_start = int((args.t_start*1000 - U.trajectory[0].time) / float(U_timestep))
			if f_start > f_end:
				print "Error: the starting time specified is after the end of the xtc."
				sys.exit(1)
		if (f_end - f_start)%args.frames_dt == 0:
			tmp_offset = 0
		else:
			tmp_offset = 1
		frames_to_process = map(lambda f:f_start + args.frames_dt*f, range(0,(f_end - f_start)//args.frames_dt+tmp_offset))
		nb_frames_to_process = len(frames_to_process)

		#initialise writer for output trajectory
		if not args.xtc_last:
			global W
			W = MDAnalysis.coordinates.xdrfile.XTC.XTCWriter(args.output_folder + '/' + output_filename, nb_atoms)
			#W_tmp = MDAnalysis.coordinates.xdrfile.XTC.XTCWriter("tmp_" + output_filename, nb_atoms)
	return

#=========================================================================================
# core functions
#=========================================================================================

def update_xtc(ts):

	global z_previous
	box_dim = ts.dimensions[2]

	#get current coordinates
	tmp_coord_current = all_atoms.coordinates()
	z_current = tmp_coord_current[:,2]
		
	#calculate displacement
	delta_z = z_current - z_previous
	nb_box_z = (np.abs(delta_z) + (1 - args.z_ratio) * box_dim) // float(box_dim)
	
	#update coords: deal with pbc
	to_add = delta_z < 0
	to_sub = delta_z > 0
	tmp_coord_current[:,2][to_add] += nb_box_z[to_add] * box_dim
	tmp_coord_current[:,2][to_sub] -= nb_box_z[to_sub] * box_dim
	z_previous = tmp_coord_current[:,2]
	
	#update coords: translate to keep > 0
	tmp_z_min = np.amin(tmp_coord_current[:,2])
	if tmp_z_min < 0:
		tmp_coord_current[:,2] += abs(tmp_z_min)
	
	#update box size: encompass all coords
	if box_dim < np.amax(tmp_coord_current[:,2]):
		box_dim = np.amax(tmp_coord_current[:,2])

	#update box size: maintain buffer
	d_buffer = (box_dim - np.amax(tmp_coord_current[:,2])) + np.amin(tmp_coord_current[:,2])
	if d_buffer < args.z_buffer:
		box_dim += args.z_buffer - d_buffer
	
	#write updated frame
	all_atoms.set_positions(tmp_coord_current)
	ts._unitcell[2,2] = box_dim
	W.write(ts)

	return

##########################################################################################
# ALGORITHM
##########################################################################################

load_MDA_universe()

#case: gro file
if args.grofilename != "no":
	
	print "to do"

	#print "Comparing structures..."
	##reference file z coords
	#z_ref=sele_ref.coordinates()[:,2]

	##current coordinates
	#tmp_new=sele_new.coordinates()

	##calculate delta z	
	#z_new=sele_new.coordinates()[:,2]
	#delta_z=z_new-z_ref

	##modify z for atoms for which new z <<< old z
	#to_add=delta_z<-0.7*U_ref.dimensions[2]
	#if numpy.size(to_add[to_add==True])>0:
		#tmp_new[:,2][to_add]+=U_new.dimensions[2]

	##modify z for atoms for which new z >>> old z
	#to_sub=delta_z>0.25*U_ref.dimensions[2]
	#if numpy.size(to_sub[to_sub==True])>0:
		#tmp_new[:,2][to_sub]-=U_new.dimensions[2]

	##update coordinates
	#sele_new.set_positions(tmp_new)
	#print "Writing new gro file..."
	#sele_new.write(outfilename+".gro")
	#print "Writing new pdb file..."
	#sele_new.write(outfilename+"_long.pdb")

#case: xtc file
else:
	print "\nProcessing trajectory..."
	#deal with 1st frame
	global z_previous
	U.trajectory[frames_to_process[0]]
	z_previous = all_atoms.coordinates()[:,2]
	
	#browse following frames
	for f_index in range(1,nb_frames_to_process):		
		#display update
		progress = '\r -processing frame ' + str(f_index+1) + '/' + str(nb_frames_to_process) + ' (every ' + str(args.frames_dt) + ' from ' + str(f_start) + ' to ' + str(f_end) + ' out of ' + str(nb_frames_xtc) + ') '
		sys.stdout.flush()
		sys.stdout.write(progress)

		#update trajectory
		ts = U.trajectory[frames_to_process[f_index]]
		update_xtc(ts)

#exit
print "\n\nFinished successfully!" "Check results in folder '" + str(args.output_folder) + "'."
sys.exit(0)
