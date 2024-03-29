# from https://greglandrum.github.io/rdkit-blog/posts/2021-08-07-rgd-and-highlighting.html

from collections import defaultdict
from io import BytesIO

import rdkit
from IPython.display import Image
from PIL import Image as pilImage
from rdkit import Chem, Geometry
from rdkit.Chem import rdDepictor, rdqueries, rdRGroupDecomposition
from rdkit.Chem.Draw import IPythonConsole, rdMolDraw2D

IPythonConsole.molSize=(450,350)
rdkit.RDLogger.DisableLog('rdApp.warning')
rdDepictor.SetPreferCoordGen(True)


def fix_Hs(mol):
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum(
        ) == 7 and not atom.IsInRing():  # for nitrogen atoms
            atom.SetNoImplicit(True)
            nbrs = list(atom.GetNeighbors())
            nonHs = [nbr.GetAtomicNum() != 1 for nbr in nbrs]
            bonds = list(atom.GetBonds())
            bondtypes = [bond.GetBondType() for bond in bonds]
            i = 0
            for bondtype in bondtypes:
                if bondtype == Chem.BondType.DOUBLE:
                    i += 1
                elif bondtype == Chem.BondType.TRIPLE:
                    i += 2
            atom.SetNumExplicitHs(3 - len(nonHs) - i +
                                    atom.GetFormalCharge())
        if atom.GetAtomicNum(
        ) == 6 and not atom.IsInRing():  # for carbon atoms
            atom.SetNoImplicit(True)
            nbrs = list(atom.GetNeighbors())
            nonHs = [nbr.GetAtomicNum() != 1 for nbr in nbrs]
            bonds = list(atom.GetBonds())
            bondtypes = [bond.GetBondType() for bond in bonds]
            i = 0
            for bondtype in bondtypes:
                if bondtype == Chem.BondType.DOUBLE:
                    i += 1
                elif bondtype == Chem.BondType.TRIPLE:
                    i += 2
            atom.SetNumExplicitHs(4 - len(nonHs) - i +
                                    atom.GetFormalCharge())
    return mol


def plot_highlighted(liga, ligb, all_intermediates, core):
    # combine edge ligands and intermediates
    ms = [liga, ligb]
    for m in ms:
        Chem.SanitizeMol(m)
    ms.extend(all_intermediates)

    # prepare core
    rdDepictor.SetPreferCoordGen(True)
    rdDepictor.Compute2DCoords(core)

    # core = Chem.DeleteSubstructs(core, Chem.MolFromSmarts('[#0]'))
    core = fix_Hs(core)
    Chem.SanitizeMol(core)

    # convert the dummy atoms in the scaffold into query atoms that match anything
    ps = Chem.AdjustQueryParameters.NoAdjustments()
    ps.makeDummiesQueries = True
    qcore = Chem.AdjustQueryProperties(core, ps)

    # prepare ligands
    mhs = [Chem.AddHs(x, addCoords=True) for x in ms]
    mms = [x for x in mhs if x.HasSubstructMatch(qcore)]
    for m in mms:
        for atom in m.GetAtoms():
            atom.SetIntProp("SourceAtomIdx", atom.GetIdx())
    ms[0].HasSubstructMatch(qcore)

    # rgroup decomposition
    groups, _ = rdRGroupDecomposition.RGroupDecompose([qcore],
                                                      mms,
                                                      asSmiles=False,
                                                      asRows=True)

    return Image(
        draw_multiple(mms,
                      groups,
                      qcore,
                      tuple(groups[0].keys())[1:],
                      nPerRow=3,
                      subImageSize=(300, 250)))

def highlight_rgroups(mol,row,core,width=350,height=200,
                      fillRings=True,legend="",
                      sourceIdxProperty="SourceAtomIdx",
                      lbls=('R1','R2','R3','R4')):
    # copy the molecule and core
    mol = Chem.Mol(mol)
    core = Chem.Mol(core)

    # -------------------------------------------
    # include the atom map numbers in the substructure search in order to
    # try to ensure a good alignment of the molecule to symmetric cores
    for at in core.GetAtoms():
        if at.GetAtomMapNum():
            at.ExpandQuery(rdqueries.IsotopeEqualsQueryAtom(200+at.GetAtomMapNum()))

    for lbl in row:
        if lbl=='Core':
            continue
        rg = row[lbl]
        for at in rg.GetAtoms():
            if not at.GetAtomicNum() and at.GetAtomMapNum() and \
            at.HasProp('dummyLabel') and at.GetProp('dummyLabel')==lbl:
                # attachment point. the atoms connected to this
                # should be from the molecule
                for nbr in at.GetNeighbors():
                    if nbr.HasProp(sourceIdxProperty):
                        mAt = mol.GetAtomWithIdx(nbr.GetIntProp(sourceIdxProperty))
                        if mAt.GetIsotope():
                            mAt.SetIntProp('_OrigIsotope',mAt.GetIsotope())
                        mAt.SetIsotope(200+at.GetAtomMapNum())
    # remove unmapped hs so that they don't mess up the depiction
    rhps = Chem.RemoveHsParameters()
    rhps.removeMapped = False
    tmol = Chem.RemoveHs(mol,rhps)
    rdDepictor.GenerateDepictionMatching2DStructure(tmol,core)

    oldNewAtomMap={}
    # reset the original isotope values and account for the fact that
    # removing the Hs changed atom indices
    for i,at in enumerate(tmol.GetAtoms()):
        if at.HasProp(sourceIdxProperty):
            oldNewAtomMap[at.GetIntProp(sourceIdxProperty)] = i
            if at.HasProp("_OrigIsotope"):
                at.SetIsotope(at.GetIntProp("_OrigIsotope"))
                at.ClearProp("_OrigIsotope")
            else:
                at.SetIsotope(0)

    # ------------------
    #  set up our colormap
    #   the three choices here are all "colorblind" colormaps

    # "Tol" colormap from https://davidmathlogic.com/colorblind
    colors = [(51,34,136),(17,119,51),(68,170,153),(136,204,238),(221,204,119),(204,102,119),(170,68,153),(136,34,85)]
    # "IBM" colormap from https://davidmathlogic.com/colorblind
    colors = [(100,143,255),(120,94,240),(220,38,127),(254,97,0),(255,176,0)]
    # Okabe_Ito colormap from https://jfly.uni-koeln.de/color/
    colors = [(230,159,0),(86,180,233),(0,158,115),(240,228,66),(0,114,178),(213,94,0),(204,121,167)]
    for i,x in enumerate(colors):
        colors[i] = tuple(y/255 for y in x)

    #----------------------
    # Identify and store which atoms, bonds, and rings we'll be highlighting
    highlightatoms = defaultdict(list)
    highlightbonds = defaultdict(list)
    atomrads = {}
    widthmults = {}

    rings = []
    for i,lbl in enumerate(lbls):
        color = colors[i%len(colors)]
        rquery = row[lbl]
        Chem.GetSSSR(rquery)
        rinfo = rquery.GetRingInfo()
        for at in rquery.GetAtoms():
            if at.HasProp(sourceIdxProperty):
                origIdx = oldNewAtomMap[at.GetIntProp(sourceIdxProperty)]
                highlightatoms[origIdx].append(color)
                atomrads[origIdx] = 0.4
        if fillRings:
            for aring in rinfo.AtomRings():
                tring = []
                allFound = True
                for aid in aring:
                    at = rquery.GetAtomWithIdx(aid)
                    if not at.HasProp(sourceIdxProperty):
                        allFound = False
                        break
                    tring.append(oldNewAtomMap[at.GetIntProp(sourceIdxProperty)])
                if allFound:
                    rings.append((tring,color))
        for qbnd in rquery.GetBonds():
            batom = qbnd.GetBeginAtom()
            eatom = qbnd.GetEndAtom()
            if batom.HasProp(sourceIdxProperty) and eatom.HasProp(sourceIdxProperty):
                origBnd = tmol.GetBondBetweenAtoms(oldNewAtomMap[batom.GetIntProp(sourceIdxProperty)],
                                                 oldNewAtomMap[eatom.GetIntProp(sourceIdxProperty)])
                bndIdx = origBnd.GetIdx()
                highlightbonds[bndIdx].append(color)
                widthmults[bndIdx] = 2

    d2d = rdMolDraw2D.MolDraw2DCairo(width,height)
    dos = d2d.drawOptions()
    dos.useBWAtomPalette()

    #----------------------
    # if we are filling rings, go ahead and do that first so that we draw
    # the molecule on top of the filled rings
    if fillRings and rings:
        # a hack to set the molecule scale
        d2d.DrawMoleculeWithHighlights(tmol,legend,dict(highlightatoms),
                                       dict(highlightbonds),
                                       atomrads,widthmults)
        d2d.ClearDrawing()
        conf = tmol.GetConformer()
        for (aring,color) in rings:
            ps = []
            for aidx in aring:
                pos = Geometry.Point2D(conf.GetAtomPosition(aidx))
                ps.append(pos)
            d2d.SetFillPolys(True)
            d2d.SetColour(color)
            d2d.DrawPolygon(ps)
        dos.clearBackground = True

    #----------------------
    # now draw the molecule, with highlights:
    d2d.DrawMoleculeWithHighlights(tmol,legend,dict(highlightatoms),dict(highlightbonds),
                                   atomrads,widthmults)
    d2d.FinishDrawing()
    png = d2d.GetDrawingText()
    return png


def draw_multiple_org(ms,groups,qcore,lbls,legends=None,nPerRow=4,subImageSize=(250,200)):
    nRows = len(ms)//nPerRow
    if len(ms)%nPerRow:
        nRows+=1
    nCols = nPerRow
    imgSize = (subImageSize[0]*nCols,subImageSize[1]*nRows)
    res = pilImage.new('RGB',imgSize)

    for i,m in enumerate(ms):
        col = i%nPerRow
        row = i//nPerRow
        if legends:
            legend = legends[i]
        else:
            legend = ''
        png = highlight_rgroups(m,groups[i],qcore,lbls=lbls,legend=legend,
                               width=subImageSize[0],height=subImageSize[1])
        bio = BytesIO(png)
        img = pilImage.open(bio)
        res.paste(img,box=(col*subImageSize[0],row*subImageSize[1]))
    bio = BytesIO()
    res.save(bio,format='PNG')
    return bio.getvalue()


def draw_multiple(ms,
                  groups,
                  qcore,
                  lbls,
                  legends=None,
                  nPerRow=4,
                  subImageSize=(250, 200)):
    nInt = len(ms) - 2
    nRows = 1 + nInt // nPerRow
    if nInt % nPerRow:
        nRows += 1
    nCols = nPerRow
    imgSize = (subImageSize[0] * nCols, subImageSize[1] * nRows)
    res = pilImage.new('RGB', imgSize)

    for i, m in enumerate(ms):
        if i < 2:
            a = i
            row = a // nPerRow
        else:
            a = i - 2
            row = a // nPerRow + 1
        col = a % nPerRow
        if row == 0:
            legend = 'Original'
        else:
            legend = f'Intermediate {i-1}'
        png = highlight_rgroups(m,
                                groups[i],
                                qcore,
                                lbls=lbls,
                                legend=legend,
                                width=subImageSize[0],
                                height=subImageSize[1])
        bio = BytesIO(png)
        img = pilImage.open(bio)
        res.paste(img, box=(col * subImageSize[0], row * subImageSize[1]))
    bio = BytesIO()
    res.save(bio, format='PNG')
    return bio.getvalue()
