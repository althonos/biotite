r"""
Mutual information as measure for coevolution of residues
=========================================================

Mutual information (MI) is a broadly used measure for the coevolution
between two residues of a sequence (citation needed) originated in
information theory.
Basically, the mutual information is a statement about how much
knowledge one already has about a distribution be knowing another
distribution:

.. math:: MI(X;Y)
   = \sum_{x \in X} \sum_{y \in Y}
   P_{X,Y}(x,y) \cdot \log_2 \frac{P_{X,Y}(x,y)}{P_{X}(x) P_{Y}(y)}

In the context of a protein the amino acid sequence is aligned to
homologous sequences. The distribution is the distribution of
amino acids in a alignment column.
When mutations in one column are often associated with certain
mutations in another alignment column, the MI between these two
positions is high.
This indicates that these two sequence positions might have evolved
together (coevolution).

For more significant results the MI of the given alignment is compared
to variants of this alignment, where each alignment column is randomly
shuffled. The results are aggregated into a Z score:

.. math:: Z_{MI} = \frac{ MI - \mu(MI_{\textrm{shuffle}}) }
                        {   \sigma(MI_{\textrm{shuffle}}) }

This example demonstrates this method on the example of hen-egg white
lysozyme (PDB: 1AKI).
At first, homologous sequences
"""

# Code source: Patrick Kunzmann
# License: BSD 3 clause

import warnings
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import biotite
import biotite.structure as struc
import biotite.structure.io.pdbx as pdbx
import biotite.sequence as seq
import biotite.sequence.io.fasta as fasta
import biotite.sequence.align as align
import biotite.sequence.graphics as graphics
import biotite.application.blast as blast
import biotite.application.clustalo as clustalo
import biotite.database.rcsb as rcsb
import biotite.database.entrez as entrez


# Get structure and sequence
pdbx_file = pdbx.PDBxFile()
pdbx_file.read(rcsb.fetch("1GUU", "mmcif"))
sequence = pdbx.get_sequence(pdbx_file)[0]
# 'use_author_fields' is set to false,
# to ensure that values in the 'res_id' annotation point to the sequence
structure = pdbx.get_structure(pdbx_file, model=1, use_author_fields=False)
structure = structure[struc.filter_amino_acids(structure)]

# Find homologous proteins in SwissProt via BLAST
app = blast.BlastWebApp("blastp", sequence, database="swissprot")
app.start()
app.join()
alignments = app.get_alignments()
hit_seqs = [sequence]
hit_ids = ["Query"]
hit_starts = [1]
IDENTITY_THESHOLD = 0.4
for ali in alignments:
    identity = align.get_sequence_identity(ali)
    # Do not include the exact same sequence -> identity < 1.0
    if identity > IDENTITY_THESHOLD and identity < 1.0:
        hit_seqs.append(ali.sequences[1])
        hit_ids.append(ali.hit_id)
        hit_starts.append(ali.hit_interval[0])

# Perform MSA
alignment = clustalo.ClustalOmegaApp.align(hit_seqs)

# Plot MSA
number_functions = []
for start in hit_starts:
    def some_func(x, start=start):
        return x + start
    number_functions.append(some_func)
fig = plt.figure(figsize=(8.0, 8.0))
ax = fig.gca()
graphics.plot_alignment_type_based(
    ax, alignment, symbols_per_line=len(alignment), labels=hit_ids,
    symbol_size=8, number_size=8, label_size=8,
    show_numbers=True, number_functions=number_functions,
    color_scheme="flower"
)
fig.tight_layout()

########################################################################
# Based on the alignment the mutual information can be calculated...

# Calculate MI Z score
def mutual_information_zscore(alignment, n_shuffle=100):
    codes = align.get_codes(alignment).T
    alph = alignment.sequences[0].alphabet
    
    mi = _mutual_information(codes, alph)
    np.random.seed(0)
    random_mi = [None] * n_shuffle
    for i in range(n_shuffle):
        shuffled_codes = _shuffle(codes)
        random_mi[i] = _mutual_information(shuffled_codes, alph)
    random_mi = np.stack(random_mi)
    mean = np.mean(random_mi, axis=0)
    std = np.std(random_mi, axis=0)
    z_score = (mi - mean) / std
    return z_score

def _shuffle(codes):
    shuffled_codes = codes.copy()
    # Shuffle each alignment column
    for i in range(len(shuffled_codes)):
        np.random.shuffle(shuffled_codes[i])
    return shuffled_codes

def _mutual_information(codes, alph):
    mi = np.zeros((len(alignment), len(alignment)))
    # Iterate over all columns to choose first column
    for i in range(codes.shape[0]):
        # Iterate over all columns to choose second column
        for j in range(codes.shape[0]):
            nrows = 0
            marginal_counts_i = np.zeros(len(alph), dtype=int)
            marginal_counts_j = np.zeros(len(alph), dtype=int)
            combined_counts = np.zeros((len(alph), len(alph)), dtype=int)
            # Iterate over all symbols in both columns
            for k in range(codes.shape[1]):
                # Skip rows where either column has a gap
                if codes[i,k] != -1 and codes[j,k] != -1:
                    marginal_counts_i[codes[i,k]] += 1
                    marginal_counts_j[codes[j,k]] += 1
                    combined_counts[codes[i,k], codes[j,k]] += 1
                    nrows += 1
            marginal_probs_i = marginal_counts_i / nrows
            marginal_probs_j = marginal_counts_j / nrows
            combined_probs = combined_counts / nrows
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mi_before_sum = (
                    combined_probs * np.log2(
                        combined_probs / (
                            marginal_probs_i[:, np.newaxis] * 
                            marginal_probs_j[np.newaxis, :]
                        )
                    )
                ).flatten()
            mi[i,j] = np.sum(mi_before_sum[~np.isnan(mi_before_sum)])
    return mi

# We are only intrested in alignment columns
# that have no gap in the C-MYB sequence
alignment = alignment[alignment.trace[:,0] != -1]
mi = mutual_information_zscore(alignment)

# Create the color map for the plot
color = colors.to_rgb(biotite.colors["dimorange"])
cmap_val = np.stack(
    [np.interp(np.linspace(0, 1, 100), [0, 1], [1, color[i]])
        for i in range(len(color))]
).transpose()
cmap = colors.ListedColormap(cmap_val)

fig = plt.figure(figsize=(8.0, 7.0))
ax = fig.gca()
im = ax.pcolormesh(mi, cmap=cmap)
cbar = fig.colorbar(im)
cbar.set_label("Z-score of mutual information")
ax.set_aspect("equal")
ax.set_xlabel("Residue position")
ax.set_ylabel("Residue position")
fig.tight_layout()
# sphinx_gallery_thumbnail_number = 2

########################################################################
# Now we can look whether there is some correlation of the pairwise
# distances of two residues and their MI...
#

# Remove elements in MI matrix for structurally unresolved residues
res_ids, _ = struc.get_residues(structure)
mask = np.array([True if i+1 in res_ids else False for i in range(len(mi))])
mi = mi[np.ix_(mask, mask)]
# Calculate pairwise residue distances for later comparison with MI
ca = structure[structure.atom_name == "CA"]
dist = struc.distance(ca.coord[:, np.newaxis], ca.coord[np.newaxis, :])
dist_flat = dist.flatten()
mi_flat = mi.flatten()
# Remove data points for distances of residues to themselves
# and for NaN values (std is 0 due to complete conservation)
mask = (dist_flat != 0) & ~np.isnan(mi_flat)
mi_flat = mi_flat[mask]
dist_flat = dist_flat[mask]

# Bin the distances based on the MI of the data point
# to calculate mean and standard deviation
BIN_WIDTH = 1.0
bin_edges = np.arange(
    int(np.floor(np.min(mi_flat))), int(np.ceil(np.max(mi_flat))), BIN_WIDTH
)
print(bin_edges)
bin_indices = np.digitize(mi_flat, bin_edges)
mean = np.zeros(len(bin_edges)-1)
std = np.zeros(len(bin_edges)-1)
for bin_i in range(len(bin_edges) - 1):
    dist_in_bin = dist_flat[bin_indices == bin_i+1]
    if len(dist_in_bin) != 0:
        mean[bin_i] = np.mean(dist_in_bin)
        std[bin_i] = np.std(dist_in_bin)

fig = plt.figure(figsize=(8.0, 4.0))
ax = fig.gca()
ax.bar(
    bin_edges[:-1], height=mean, width=BIN_WIDTH,
    color=biotite.colors["lightorange"], align="edge"
)
ax.errorbar(
    bin_edges[:-1]+BIN_WIDTH/2, mean, yerr=std,
    ecolor="black", linestyle="None"
)
ax.scatter(
    mi_flat, dist_flat,
    s=4, color=biotite.colors["dimorange"], edgecolors="None", zorder=10
)
ax.set_xlabel("Z-score of mutual information")
ax.set_ylabel("Cα distance")
ax.set_xlim(bin_edges[0], bin_edges[-1])
fig.tight_layout()

plt.show()