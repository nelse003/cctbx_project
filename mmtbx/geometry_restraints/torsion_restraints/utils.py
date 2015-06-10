from __future__ import division
from libtbx.utils import Sorry
from iotbx.pdb import common_residue_names_get_class
from iotbx.pdb import amino_acid_codes, input
from cctbx.array_family import flex
from libtbx import group_args
import math
import mmtbx.alignment
import sys

def process_reference_files(
      reference_file_list,
      log=None):
  if log is None:
    log = sys.stdout
  reference_hierarchy_list = []
  for file in reference_file_list:
    pdb_io = input(file)
    cur_hierarchy = pdb_io.construct_hierarchy()
    cur_hierarchy.reset_i_seq_if_necessary()
    ter_indices = pdb_io.ter_indices()
    if ter_indices is not None:
      check_for_internal_chain_ter_records(
        pdb_hierarchy=cur_hierarchy,
        ter_indices=ter_indices)
    reference_hierarchy_list.append(cur_hierarchy)
  return reference_hierarchy_list

def get_reference_dihedral_proxies(
      reference_hierarchy_list,
      reference_file_list,
      mon_lib_srv=None,
      ener_lib=None,
      crystal_symmetry=None,
      log=None):
  from mmtbx.monomer_library import server
  if log is None:
    log = sys.stdout
  if mon_lib_srv is None:
    mon_lib_srv = server.server()
  if ener_lib is None:
    ener_lib = server.ener_lib()
  reference_dihedral_proxies = {}
  for file_name, pdb_hierarchy in zip(reference_file_list,
                                      reference_hierarchy_list):
    dihedral_proxies = get_complete_dihedral_proxies(
                         pdb_hierarchy=pdb_hierarchy,
                         mon_lib_srv=mon_lib_srv,
                         ener_lib=ener_lib,
                         crystal_symmetry=crystal_symmetry,
                         log=log)
    reference_dihedral_proxies[file_name]=dihedral_proxies
  return reference_dihedral_proxies

def get_complete_dihedral_proxies(
      pdb_hierarchy=None,
      file_name=None,
      raw_records=None,
      mon_lib_srv=None,
      ener_lib=None,
      crystal_symmetry=None,
      log=None):
  #
  # This function is called only for reference files, that were not processed
  # yet. For the main file only get_dihedrals_and_phi_psi below is called.
  #
  assert [pdb_hierarchy,
          file_name,
          raw_records].count(None) == 2
  from mmtbx.monomer_library import server, pdb_interpretation
  import cStringIO
  if log is None:
    log = sys.stdout
  if mon_lib_srv is None:
    mon_lib_srv = server.server()
  if ener_lib is None:
    ener_lib = server.ener_lib()
  if pdb_hierarchy is not None:
    raw_records = pdb_hierarchy.as_pdb_string()
  if raw_records is not None:
    if (isinstance(raw_records, str)):
      raw_records = flex.split_lines(raw_records)
  work_params = pdb_interpretation.master_params.extract()
  work_params.c_beta_restraints=False
  work_params.automatic_linking.link_none=True
  work_params.clash_guard.nonbonded_distance_threshold = None

  processed_pdb_file_local = \
    pdb_interpretation.process(
      mon_lib_srv=mon_lib_srv,
      ener_lib=ener_lib,
      params=work_params,
      file_name=file_name,
      raw_records=raw_records,
      strict_conflict_handling=False,
      crystal_symmetry=crystal_symmetry,
      force_symmetry=True,
      log=cStringIO.StringIO(),
      substitute_non_crystallographic_unit_cell_if_necessary=True)
  return get_dihedrals_and_phi_psi(processed_pdb_file_local)

def get_dihedrals_and_phi_psi(processed_pdb_file):
  from mmtbx.conformation_dependent_library import generate_protein_threes
  grm = processed_pdb_file.geometry_restraints_manager()
  dihedral_proxies = grm.get_dihedral_proxies().deep_copy()
  for three in generate_protein_threes(
      hierarchy=processed_pdb_file.all_chain_proxies.pdb_hierarchy,
      geometry=None):
    phi_proxy, psi_proxy = three.get_dummy_dihedral_proxies()
    dihedral_proxies.extend([phi_proxy, psi_proxy])
  return dihedral_proxies

def modernize_rna_resname(resname):
  if common_residue_names_get_class(resname,
       consider_ccp4_mon_lib_rna_dna=True) == "common_rna_dna" or \
     common_residue_names_get_class(resname,
       consider_ccp4_mon_lib_rna_dna=True) == "ccp4_mon_lib_rna_dna":
    tmp_resname = resname.strip()
    if len(tmp_resname) == 1:
      return "  "+tmp_resname
    elif len(tmp_resname) == 2:
      if tmp_resname[0:1].upper() == 'D':
        return " "+tmp_resname.upper()
      elif tmp_resname[1:].upper() == 'D':
        return " D"+tmp_resname[0:1].upper()
      elif tmp_resname[1:].upper() == 'R':
        return "  "+tmp_resname[0:1].upper()
    elif tmp_resname in ["ADE", "CYT", "GUA", "URI"]:
      return "  "+tmp_resname[0:1].upper()
  return resname

def modernize_rna_atom_name(atom):
   new_atom = atom.replace('*',"'")
   if new_atom == " O1P":
     new_atom = " OP1"
   elif new_atom == " O2P":
     new_atom = " OP2"
   return new_atom

def build_name_hash(pdb_hierarchy):
  i_seq_name_hash = dict()
  for atom in pdb_hierarchy.atoms():
    atom_name = atom.pdb_label_columns()[0:4]
    resname = atom.pdb_label_columns()[5:8]
    updated_resname = modernize_rna_resname(resname)
    if common_residue_names_get_class(updated_resname) == "common_rna_dna":
      updated_atom = modernize_rna_atom_name(atom=atom_name)
    else:
      updated_atom = atom_name
    key = updated_atom+atom.pdb_label_columns()[4:5]+\
          updated_resname+atom.pdb_label_columns()[8:]+\
          atom.segid
    i_seq_name_hash[atom.i_seq]=key
  return i_seq_name_hash

def build_i_seq_hash(pdb_hierarchy):
  name_i_seq_hash = dict()
  for atom in pdb_hierarchy.atoms():
    atom_name = atom.pdb_label_columns()[0:4]
    resname = atom.pdb_label_columns()[5:8]
    updated_resname = modernize_rna_resname(resname)
    if common_residue_names_get_class(updated_resname) == "common_rna_dna":
      updated_atom = modernize_rna_atom_name(atom=atom_name)
    else:
      updated_atom = atom_name
    key = updated_atom+atom.pdb_label_columns()[4:5]+\
          updated_resname+atom.pdb_label_columns()[8:]+\
          atom.segid
    name_i_seq_hash[key]=atom.i_seq
  return name_i_seq_hash

def id_str (chain_id,
            resseq,
            resname,
            icode,
            altloc,
            segid=None,
            ignore_altloc=False) :
  base = "%2s%4s%1s" % (chain_id, resseq, icode)
  if (not ignore_altloc) :
    base += "%1s" % altloc
  else :
    base += " "
  base += "%3s" % resname
  if (segid is not None) :
    base += " segid='%4s'" % segid
  return base


def build_xyz_hash(pdb_hierarchy):
  name_xyz_hash = dict()
  for atom in pdb_hierarchy.atoms():
    name_xyz_hash[atom.pdb_label_columns()]=atom.xyz
  return name_xyz_hash

def build_resid_hash(pdb_hierarchy):
  resid_hash = dict()
  for rg in pdb_hierarchy.residue_groups():
    resid = rg.resseq_as_int()
    for atom in rg.atoms():
      resid_hash[atom.i_seq]=resid
  return resid_hash

def build_i_seq_xyz_hash(pdb_hierarchy):
  i_seq_xyz_hash = dict()
  for atom in pdb_hierarchy.atoms():
    i_seq_xyz_hash[atom.i_seq] = atom.xyz
  return i_seq_xyz_hash

def build_element_hash(pdb_hierarchy):
  i_seq_element_hash = dict()
  for atom in pdb_hierarchy.atoms():
    i_seq_element_hash[atom.i_seq]=atom.element
  return i_seq_element_hash

def build_chain_hash(pdb_hierarchy):
  chain_hash = dict()
  for chain in pdb_hierarchy.chains():
    for atom in chain.atoms():
      chain_hash[atom.i_seq] = chain.id
  return chain_hash

def build_segid_hash(pdb_hierarchy):
  segid_hash = dict()
  for atom in pdb_hierarchy.atoms():
    segid_hash[atom.i_seq] = atom.segid
  return segid_hash

def build_sym_atom_hash(pdb_hierarchy):
  sym_atom_hash = dict()
  for model in pdb_hierarchy.models():
    for chain in model.chains():
      for conformer in chain.conformers():
        for residue in conformer.residues():
          if residue.resname.upper() in ['ASP', 'GLU', 'PHE', 'TYR']:
            if residue.resname.upper() == 'ASP':
              atom1 = ' OD1'
              atom2 = ' OD2'
            elif residue.resname.upper() == 'GLU':
              atom1 = ' OE1'
              atom2 = ' OE2'
            elif residue.resname.upper() in ['PHE', 'TYR']:
              atom1 = ' CD1'
              atom2 = ' CD2'
            atom1_i_seq = None
            atom2_i_seq = None
            for atom in residue.atoms():
              if atom.name == atom1:
                atom1_i_seq = atom.i_seq
              elif atom.name == atom2:
                atom2_i_seq = atom.i_seq
            if atom1_i_seq != None and atom2_i_seq != None:
              sym_atom_hash[atom1_i_seq] = atom2_i_seq
              sym_atom_hash[atom2_i_seq] = atom1_i_seq
  return sym_atom_hash

def angle_distance(angle1, angle2):
  distance = math.fabs(angle1 - angle2)
  if distance > 180.0:
    distance -= 360.0
  return math.fabs(distance)

def get_angle_average(angles):
  local_angles = []
  for angle in angles:
    if angle is not None:
      local_angles.append(angle)
  n_angles = len(local_angles)
  if n_angles < 1:
    return None
  sum = 0.0
  a1 = local_angles[0]
  if a1 > 180.0:
    a1 -= 360.0
  elif a1 < -180.0:
    a1 += 360.0
  sum += a1
  for angle in local_angles[1:]:
    a2 = angle
    if (a1 - a2) > 180.0:
      a2 += 360.0
    elif (a1 - a2) < -180.0:
      a2 -= 360.0
    sum += a2
  average = sum / n_angles
  return average

def _alignment(sequences,
               padded_sequences,
               structures,
               log=None):
  #
  # used in torsion_ncs.py
  #
  if(log is None): log = sys.stdout
  res_match_hash = {}
  model_mseq_res_hash = {}
  ref_mseq_res_hash = {}
  model_seq = sequences[0]
  model_seq_padded = padded_sequences[0]
  model_structures = structures[0]
  ref_seq = sequences[1]
  ref_seq_padded = padded_sequences[1]
  ref_structures = structures[1]
  for struct in model_structures:
    resname = struct.rg.atoms()[0].pdb_label_columns()[5:8]
    if resname.upper() == "MSE":
      resname = "MET"
    updated_resname = modernize_rna_resname(resname)
    key = struct.rg.atoms()[0].pdb_label_columns()[4:5]+\
          updated_resname+struct.rg.atoms()[0].pdb_label_columns()[8:]+\
          struct.rg.atoms()[0].segid
    model_mseq_res_hash[struct.i_seq] = key
  for struct in ref_structures:
    resname = struct.rg.atoms()[0].pdb_label_columns()[5:8]
    if resname.upper() == "MSE":
      resname = "MET"
    updated_resname = modernize_rna_resname(resname)
    key = struct.rg.atoms()[0].pdb_label_columns()[4:5]+\
          updated_resname+struct.rg.atoms()[0].pdb_label_columns()[8:]+\
          struct.rg.atoms()[0].segid
    ref_mseq_res_hash[struct.i_seq] = key
  if model_seq == ref_seq:
    pg = mmtbx.alignment.pairwise_global(
           model_seq,
           ref_seq)
  else:
    pg = mmtbx.alignment.pairwise_global(
           model_seq_padded,
           ref_seq_padded)
  offset_i = 0
  offset_j = 0
  i = 0
  j = 0
  seq_j = pg.result2[j]
  for seq_i in pg.result1:
    seq_j = pg.result2[j]
    if seq_i == seq_j and seq_i != 'X' and seq_j != 'X':
      res_match_hash[model_mseq_res_hash[i-offset_i]] = \
        ref_mseq_res_hash[j-offset_j]
      i += 1
      j += 1
    else:
      if seq_i == 'X' and seq_j == 'X':
        i += 1
        j += 1
        offset_i += 1
        offset_j += 1
      elif (seq_i == 'X' and seq_j == '-') or \
           (seq_i == '-' and seq_j == 'X'):
        i += 1
        j += 1
        offset_i += 1
        offset_j += 1
      elif seq_i == 'X':
        i += 1
        j += 1
        offset_i += 1
      elif seq_j == 'X':
        i += 1
        j += 1
        offset_j += 1
      elif seq_i == '-':
        i += 1
        j += 1
        offset_i += 1
      elif seq_j == '-':
        i += 1
        j += 1
        offset_j += 1
      else:
        i += 1
        j += 1
  return res_match_hash

def chain_from_selection(chain, selection):
  from iotbx.pdb.hierarchy import new_hierarchy_from_chain
  new_hierarchy = new_hierarchy_from_chain(chain=chain).select(selection)

def hierarchy_from_selection(pdb_hierarchy, selection, log):
  import iotbx.pdb.hierarchy
  temp_hierarchy = pdb_hierarchy.select(selection)
  altloc = None
  hierarchy = iotbx.pdb.hierarchy.root()
  model = iotbx.pdb.hierarchy.model()
  for chain in temp_hierarchy.chains():
    for conformer in chain.conformers():
      if not conformer.is_protein() and not conformer.is_na():
        continue
      elif altloc is None or conformer.altloc == altloc:
        model.append_chain(chain.detached_copy())
        altloc = conformer.altloc
      else:
        print >> log, \
        "* Multiple alternate conformations found, using altid %s *" \
        % altloc
        continue
  if len(model.chains()) != 1:
    raise Sorry("more than one chain in selection")
  hierarchy.append_model(model)
  return hierarchy

def is_residue_in_selection(i_seqs, selection):
  assert isinstance(selection, flex.bool)
  for i_seq in i_seqs:
    if not selection[i_seq]:
      return False
  return True

def extract_sequence_and_sites(pdb_hierarchy, selection):
  # used in torsion_ncs
  assert isinstance(selection, flex.bool)
  seq = []
  result = []
  padded_seq = []
  last_resseq = 0
  counter = 0
  for model in pdb_hierarchy.models():
    for chain in model.chains():
      is_na = False
      for conformer in chain.conformers():
        if conformer.is_na():
          is_na = True
      for rg in chain.residue_groups():
        if(len(rg.unique_resnames())==1):
          resname = rg.unique_resnames()[0]
          if is_na:
            olc = get_nucleic_acid_one_letter_code(resname)
          else:
            olc= \
            amino_acid_codes.one_letter_given_three_letter.get(resname,"X")
          atoms = rg.atoms()
          i_seqs = atoms.extract_i_seq()
          if(olc!="X") and is_residue_in_selection(i_seqs, selection):
            seq.append(olc)
            resseq = rg.resseq_as_int()
            if (resseq > (last_resseq + 1)) :
              for x in range(resseq - last_resseq - 1) :
                padded_seq.append('X')
            last_resseq = resseq
            result.append(group_args(i_seq = counter, rg = rg))
            padded_seq.append(olc)
            counter += 1
  return "".join(seq), "".join(padded_seq), result

def get_nucleic_acid_one_letter_code(resname):
  olc=amino_acid_codes.one_letter_given_three_letter.get(resname,"X")
  if olc != "X":
    return "X"
  if resname[0:2] == "  ":
    return resname[2]
  elif resname[0] == " " and (resname[1] == "D" or resname[1] == "d"):
    return resname[2]
  else:
    return resname[0]

def get_unique_segid(chain):
  segid = None
  for atom in chain.atoms():
    if segid is None:
      segid = atom.segid
    elif segid != atom.segid:
      return None
  return segid

def check_for_internal_chain_ter_records(
      pdb_hierarchy,
      ter_indices):
  chains = pdb_hierarchy.chains()
  atoms = pdb_hierarchy.atoms()
  chain_ter_matches = {}
  chain_ranges = {}
  for chain in chains:
    found_conformer = False
    for conformer in chain.conformers():
      if not conformer.is_protein() and not conformer.is_na():
        continue
      else:
        found_conformer = True
    if not found_conformer:
      continue
    min = None
    max = None
    for atom in chain.atoms():
      if min is not None:
        if atom.i_seq < min:
          min = atom.i_seq
      else:
        min = atom.i_seq
      if max is not None:
        if atom.i_seq > max:
          max = atom.i_seq
      else:
        max = atom.i_seq
    if chain_ranges.get(chain.id) is None:
      chain_ranges[chain.id] = []
    chain_ranges[chain.id].append( (min, max) )

  #find min/max for all chains with same id
  reduced_chain_ranges = {}
  for key in chain_ranges.keys():
    min_all = None
    max_all = None
    ranges = chain_ranges[key]
    for min, max in ranges:
      if min_all is not None:
        if min < min_all:
          min_all = min
      else:
        min_all = min
      if max_all is not None:
        if max > max_all:
          max_all = max
      else:
        max_all = max
    reduced_chain_ranges[key] = (min_all, max_all)
  for ter_id in ter_indices:
    for key in reduced_chain_ranges.keys():
      min, max = reduced_chain_ranges[key]
      if ter_id > min and ter_id < max:
        raise Sorry("chain '%s' contains one or more "%(key)+
                    "errant TER cards.\nPlease remove and try again.")

def get_torsion_id(dp,
                   name_hash,
                   phi_psi=False,
                   chi_only=False,
                   omega=False):
  #
  # used in torsion_ncs
  id = None
  chi_atoms = False
  atom_list = []
  altloc = None
  if phi_psi:
    return name_hash[dp.i_seqs[1]][4:]
  elif omega:
    #LIMITATION: doesn't work with segIDs currently
    return name_hash[dp.i_seqs[0]][4:], \
           name_hash[dp.i_seqs[3]][4:]
  for i_seq in dp.i_seqs:
    cur_id = name_hash[i_seq][4:]
    atom = name_hash[i_seq][:4]
    atom_list.append(atom)
    cur_altloc = name_hash[i_seq][4:5]
    if id == None:
      id = cur_id
    if cur_altloc != " " and altloc:
      altloc = cur_altloc
    elif cur_id != id:
      return None
    resname = cur_id[1:4]
    if common_residue_names_get_class(resname,
         consider_ccp4_mon_lib_rna_dna=True) != "common_amino_acid":
      return None
    if chi_only:
      if atom not in [' N  ', ' CA ', ' C  ', ' O  ', ' CB ', ' OXT']:
        chi_atoms = True
  if chi_only and not chi_atoms:
    return None
  return id

def get_c_alpha_hinges(pdb_hierarchy,
                       xray_structure=None,
                       selection=None):
  #
  # used in torsion_ncs
  c_alphas = []
  c_alpha_hinges = {}
  if xray_structure is not None:
    sites_cart = xray_structure.sites_cart()
  else:
    sites_cart = pdb_hierarchy.atoms().extract_xyz()
  if selection is None:
    selection = flex.bool(len(sites_cart), True)
  for model in pdb_hierarchy.models():
    for chain in model.chains():
      for residue_group in chain.residue_groups():
        for atom_group in residue_group.atom_groups():
          cur_ca = None
          cur_c = None
          cur_o = None
          cur_n = None
          cur_h = None
          for atom in atom_group.atoms():
            if atom.name == " CA ":
              cur_ca = atom
            elif atom.name == " C  ":
              cur_c = atom
            elif atom.name == " N  ":
              cur_n = atom
            elif atom.name == " O  ":
              cur_o = atom
            elif atom.name == " H  ":
              cur_h = atom
          if cur_ca is not None and cur_c is not None and \
             cur_n is not None and cur_o is not None:
            if( (not selection[cur_ca.i_seq]) or
                (not selection[cur_c.i_seq])  or
                (not selection[cur_n.i_seq])  or
                (not selection[cur_o.i_seq]) ):
              continue
            moving_tpl = (cur_n, cur_c, cur_o)
            if cur_h is not None:
              moving_tpl += tuple([cur_h])
            c_alphas.append( (cur_ca, moving_tpl) )
  for i, ca in enumerate(c_alphas):
    if i < 1 or i == (len(c_alphas)-1):
      continue
    current = ca
    previous = c_alphas[i-1]
    next = c_alphas[i+1]
    prev_connected = check_residues_are_connected(previous[0], current[0])
    next_connected = check_residues_are_connected(current[0], next[0])
    if prev_connected and next_connected:
      nodes = (previous[0].i_seq, next[0].i_seq)
      moving = (previous[1][1].i_seq, previous[1][2].i_seq, next[1][0].i_seq)
      if len(next[1]) > 3:
        moving += tuple([next[1][3].i_seq])
      c_alpha_hinges[current[0].i_seq] = [nodes, moving]
  return c_alpha_hinges

def check_residues_are_connected (ca_1, ca_2, max_sep=4.0, min_sep=0.) :
  from scitbx import matrix
  ca_1_mat = matrix.col(ca_1.xyz)
  ca_2_mat = matrix.col(ca_2.xyz)
  dist = (ca_1_mat - ca_2_mat).length()
  if (dist > max_sep) or (dist < min_sep) :
    return False
  return True

def is_protein_chain(chain):
  for conformer in chain.conformers():
    if not conformer.is_protein():
      return False
  return True

def prepare_map(
      fmodel,
      exclude_free_r_reflections=False):
  map_obj = fmodel.electron_density_map()
  fft_map = map_obj.fft_map(resolution_factor = 1./4,
    map_type = "2mFo-DFc", use_all_data=(
      not exclude_free_r_reflections))
  fft_map.apply_sigma_scaling()
  target_map_data = fft_map.real_map_unpadded()
  fft_map = map_obj.fft_map(resolution_factor = 1./4,
    map_type = "mFo-DFc", use_all_data=(
      not exclude_free_r_reflections))
  fft_map.apply_sigma_scaling()
  residual_map_data = fft_map.real_map_unpadded()
  return target_map_data, residual_map_data