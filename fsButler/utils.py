import re
import numpy as np

import lsst.afw.table as afwTable
import lsst.afw.geom as afwGeom
import lsst.afw.image as afwImage
import lsst.analysis.utils as utils
import lsst.afw.display.ds9 as ds9

"""
Utility functions to process data elements delivered by fsButler
"""

#TODO: Make these configurable options

_fixedFields = ["id", "coord"]

_fixedPatterns = []

_suffixableFields = ["parent",
                     "deblend.nchild",
                     "classification.extendedness",
                     "flags.pixel.bad",
                     #"flux.kron.radius",
                     "flags.pixel.edge",
                     "flags.pixel.interpolated.any",
                     "flags.pixel.interpolated.center",
                     "flags.pixel.saturated.any",
                     "flags.pixel.saturated.center"]

_suffixablePatterns = ["flux.zeromag*",
                       "flux.psf*",
                       "cmodel*",
                       "centroid*",
                       "seeing*",
                       "exptime*",
                       "multId*"]

_suffixRegex = re.compile(r'(_[grizy])$')
_bandRegex = re.compile(r'(\.[grizy])$')

_zeroMagField = afwTable.Field["F"]("flux.zeromag",
                                    "The flux corresponding to zero magnitude.")
_zeroMagErrField = afwTable.Field["F"]("flux.zeromag.err",
                                       "The flux error corresponding to zero magnitude.")
_stellarField = afwTable.Field["Flag"]("stellar",
                                       "If true, the object is known to be a star if false it's known not to be a star.")
_magAutoField = afwTable.Field["F"]("mag.auto",
                                    "The magnitude computed by SExtractor in the HST catalog.")
_seeingField = afwTable.Field["F"]("seeing",
                                    "The PSF FWHM.")
_exptimeField = afwTable.Field["F"]("exptime",
                                    "Exposure time.")
_idField = afwTable.Field["L"]("multId",
                               "Multiple id, this field is in place to keep track of the ids of the matches in other catalogs/bands")

def _getFilterSuffix(filterSuffix):
    if filterSuffix == 'HSC-G':
        return '_g'
    elif filterSuffix == 'HSC-R':
        return '_r'
    elif filterSuffix == 'HSC-I':
        return '_i'
    elif filterSuffix == 'HSC-Z':
        return '_z'
    elif filterSuffix == 'HSC-Y':
        return '_y'
    else:
        return filterSuffix

def _suffixOrder(suffix):
    if suffix == '_g':
        return 1
    if suffix == '_r':
        return 2
    if suffix == '_i':
        return 3
    if suffix == '_z':
        return 4
    if suffix == '_y':
        return 5

def _bandOrder(suffix):
    if suffix == 'g':
        return 1
    if suffix == 'r':
        return 2
    if suffix == 'i':
        return 3
    if suffix == 'z':
        return 4
    if suffix == 'y':
        return 5

def getCatSuffixes(cat):
    suffixes = []
    for schemaItem in cat.getSchema():
        fieldName = schemaItem.getField().getName()
        match = _suffixRegex.search(fieldName)
        if match:
            suffix = match.group(1)
            if suffix not in suffixes:
                suffixes.append(suffix) 
    suffixes.sort(key=_suffixOrder)
    return suffixes
    
def getCatBands(cat):
    bands = []
    for schemaItem in cat.getSchema():
        fieldName = schemaItem.getField().getName()
        match = _bandRegex.search(fieldName)
        if match:
            band = match.group(1)[-1]
            if band not in bands:
                bands.append(band) 
    bands.sort(key=_bandOrder)
    return bands

def createSchemaMapper(cat, cat2=None, filterSuffix=None, withZeroMagFlux=False,
                       withStellar=False, withSeeing=False, withExptime=False):

    if cat2 is not None and filterSuffix:
        raise ValueError("Can't use filterSuffix for two catalogs")

    suffixes = getCatSuffixes(cat)
    if len(suffixes) > 0 and filterSuffix is not None:
        raise ValueError("Can't add a suffix to a catalog that already has suffixes")

    schema = cat.getSchema()
    scm = afwTable.SchemaMapper(schema)

    # First fixed fields and patterns
    for f in _fixedFields: 
        scm.addMapping(schema.find(f).getKey())
    for p in _fixedPatterns:
        for f in schema.extract(p):
            scm.addMapping(schema.find(f).getKey())

    # Now suffixable fields and patterns
    if filterSuffix is not None:
        suffix = _getFilterSuffix(filterSuffix)
        scm.addOutputField(_idField.copyRenamed("multId"+suffix))
    for f in _suffixableFields:
        if filterSuffix is not None:
            field = schema.find(f).getField()
            newField = field.copyRenamed(f + suffix)
            scm.addMapping(schema.find(f).getKey(), newField)
        else:
            if len(suffixes) == 0:
                scm.addMapping(schema.find(f).getKey())
            else:
                for s in suffixes:
                    scm.addMapping(schema.find(f+s).getKey())
    for p in _suffixablePatterns:
        for f in schema.extract(p):
            if filterSuffix:
                field = schema.find(f).getField()
                newField = field.copyRenamed(f + suffix)
                scm.addMapping(schema.find(f).getKey(), newField)
            else:
                # The extract command gets all the suffixes for me
                scm.addMapping(schema.find(f).getKey())

    if cat2 is not None:
        suffixes2 = getCatSuffixes(cat2)
        schema2 = cat2.getSchema()
        for f in _suffixableFields:
            for s in suffixes2:
                field = schema2.find(f+s).getField()
                scm.addOutputField(field)
        for p in _suffixablePatterns:
            for f in schema2.extract(p):
                # The extract command gets the suffixes for me
                field = schema2.find(f).getField()
                scm.addOutputField(field)

    if withZeroMagFlux:
        if filterSuffix:
            scm.addOutputField(_zeroMagField.copyRenamed("flux.zeromag"+suffix))
            scm.addOutputField(_zeroMagErrField.copyRenamed("flux.zeromag.err"+suffix))
        else:
            if len(suffixes) == 0:
                scm.addOutputField(_zeroMagField)
                scm.addOutputField(_zeroMagErrField)
            else:
                for s in suffixes:
                    scm.addOutputField(_zeroMagField.copyRenamed("flux.zeromag"+s))
                    scm.addOutputField(_zeroMagErrField.copyRenamed("flux.zeromag.err"+s))

    if withSeeing:
        if filterSuffix:
            scm.addOutputField(_seeingField.copyRenamed("seeing"+suffix))
        else:
            if len(suffixes) == 0:
                scm.addOutputField(_seeingField)
            else:
                for s in suffixes:
                    scm.addOutputField(_seeingField.copyRenamed("seeing"+s))

    if withExptime:
        if filterSuffix:
            scm.addOutputField(_exptimeField.copyRenamed("exptime"+suffix))
        else:
            if len(suffixes) == 0:
                scm.addOutputField(_exptimeField)
            else:
                for s in suffixes:
                    scm.addOutputField(_exptimeField.copyRenamed("exptime"+s))

    if withStellar:
        scm.addOutputField(_stellarField)
        scm.addOutputField(_magAutoField)

    return scm

def goodSources(cat):
    # Get the list of sources with bad flags
    bad = reduce(lambda x, y: np.logical_or(x, cat.get(y)),
                 ["flags.pixel.edge",
                  "flags.pixel.bad",
                  "flags.pixel.saturated.center"],
                  False)
    good = np.logical_not(bad)
    # Get rid of objects that have children, i.e. the deblender thinks it's a set of objects
    good = np.logical_and(good, cat.get("deblend.nchild") == 0)
    return good

def strictMatch(cat1, cat2, matchRadius=1*afwGeom.arcseconds, includeMismatches=True):
    """
    Match two catalogs using a one to one relation where each match is the closest
    object
    """
    
    mc = afwTable.MatchControl()
    mc.includeMismatches = includeMismatches

    #matched = afwTable.matchRaDec(cat1, cat2, matchRadius, True)
    matched = afwTable.matchRaDec(cat1, cat2, matchRadius, mc)

    bestMatches = {}
    noMatch = []
    for m1, m2, d in matched:
        if m2 is None:
            noMatch.append(m1)
        else:
            id = m2.getId()
            if id not in bestMatches:
                bestMatches[id] = (m1, m2, d)
            else:
                if d < bestMatches[id][2]:
                    bestMatches[id] = (m1, m2, d)

    if includeMismatches:
        print "{0} objects from {1} in the first catalog had no match in the second catalog.".format(len(noMatch), len(cat1))
        print "{0} objects from the first catalog with a match in the second catalog were not the closest match.".format(len(matched) - len(noMatch) - len(bestMatches))

    scm = createSchemaMapper(cat1, cat2)
    schema = scm.getOutputSchema()
    cat = afwTable.SimpleCatalog(schema)
    cat.reserve(len(bestMatches))
    cat2Fields = []; cat2Keys = []; catKeys = []
    schema2 = cat2.getSchema()
    suffixes = getCatSuffixes(cat2)
    for suffix in suffixes:
        cat2Fields.extend(schema2.extract("*" + suffix).keys())
    for f in cat2Fields:
        cat2Keys.append(schema2.find(f).key)
        catKeys.append(schema.find(f).key)
    for id in bestMatches:
        m1, m2, d = bestMatches[id]
        record = cat.addNew()
        record.assign(m1, scm)
        for i in range(len(cat2Keys)):
            record.set(catKeys[i], m2.get(cat2Keys[i]))
    return cat

def matchMultiBand(butler, dataType, filters=['HSC-G', 'HSC-R', 'HSC-I', 'HSC-Z', 'HSC-Y'], **kargs):
    cats = []
    for f in filters:
        cat = butler.fetchDataset(dataType, filterSuffix=f, filter=f, **kargs)
        cats.append(cat)

    matched = cats[0]

    for i in range(1, len(filters)):
        matched = strictMatch(matched, cats[i])
    
    return matched

def buildXY(hscCat, sgTable, matchRadius=1*afwGeom.arcseconds, includeMismatches=True):

    mc = afwTable.MatchControl()
    mc.includeMismatches = includeMismatches

    print "Matching with HST catalog"
    matchedSG = afwTable.matchRaDec(hscCat, sgTable, matchRadius, mc)
    print "Found {0} matches with HST objects".format(len(matchedSG))
    
    # Build truth table
    stellar = {}
    classKey = sgTable.getSchema().find('mu.class').key
    magAutoKey = sgTable.getSchema().find('mag.auto').key
    noMatch = []
    for m1, m2, d in matchedSG:
        if m2 is None:
            noMatch.append(m1.getId())
        else:
            id = m2.getId()
            isStar = (m2.get(classKey) == 2)
            magAuto = m2.get(magAutoKey)
            if id not in stellar:
                stellar[id] = [isStar, magAuto, d, m1]
            else:
                if d < stellar[id][2]:
                    stellar[id] = [isStar, magAuto, d, m1] # Only keep closest for now

    if includeMismatches:
        print "{0} objects from {1} in the HSC catalog had no match in the HST catalog.".format(len(noMatch), len(hscCat))
        print "{0} objects from the HSC catalog with a match in the HST catalog were not the closest match.".format(len(matchedSG) - len(noMatch) - len(stellar))

    print "Of which I picked {0}".format(len(stellar)) 

    scm = createSchemaMapper(hscCat, withStellar=True)
    schema = scm.getOutputSchema()
    cat = afwTable.SourceCatalog(schema)
    cat.reserve(len(stellar))
    stellarKey = schema.find('stellar').key
    magAutoKey = schema.find('mag.auto').key

    for id in stellar:
        isStar, magAuto, d, m2 = stellar[id]
        record = cat.addNew()
        record.assign(m2, scm)
        record.set(stellarKey, isStar)
        record.set(magAutoKey, magAuto)

    if includeMismatches:
        return cat, noMatch

    return cat

def getRecord(objId, fsButler, dataType='deepCoadd'):
    info = utils.makeMapperInfo(fsButler.butler)
    if 'Coadd' in dataType or 'coadd' in dataType:
        dataId = info.splitCoaddId(objId)
    else:
        dataId = info.splitExposureId(objId)
    dataId.pop('objId')
    src = fsButler.butler.get(dataType+'_src', immediate=True, **dataId)
    record = src[objId == src.get("id")][0]
    return record

def getParent(objId, fsButler, dataType='deepCoadd'):
    record = getRecord(objId, fsButler, dataType='deepCoadd')
    info = utils.makeMapperInfo(fsButler.butler)
    parentId = record.getParent()
    if parentId == 0:
        print "This object has no parent"
        return None
    if 'Coadd' in dataType or 'coadd' in dataType:
        dataId = info.splitCoaddId(parentId)
    else:
        dataId = info.splitExposureId(parentId)
    dataId.pop('objId')
    src = fsButler.butler.get(dataType+'_src', immediate=True, **dataId)
    parent = src[objId == src.get("id")][0]
    return parent

def getMultId(cat):
   bands = getCatBands(cat)
   multIds = np.zeros((len(cat),), dtype=[(b, 'int64') for b in bands])
   for b in bands:
       multIds[b] = cat.get('multId.'+b)
   return multIds

def displayObject(objId, fsButler, dataType='deepCoadd', nPixel=15, frame=None):
    #TODO: Enable single exposure objects
    info = utils.makeMapperInfo(fsButler.butler)
    if 'Coadd' in dataType or 'coadd' in dataType:
        dataId = info.splitCoaddId(objId)
    else:
        dataId = info.splitExposureId(objId)
    dataId.pop('objId')
    src = fsButler.butler.get(dataType+'_src', immediate=True, **dataId)
    src = src[objId == src.get("id")][0]
    coord = src.getCoord()
    de = fsButler.butler.get(dataType, **dataId)
    pixel = de.getWcs().skyToPixel(coord)
    pixel = afwGeom.Point2I(pixel)
    bbox = afwGeom.Box2I(pixel, pixel)
    bbox.grow(nPixel)
    im = afwImage.ExposureF(de, bbox, afwImage.PARENT)
    ds9.mtv(im, frame=frame)
    return im

def showCoaddInputs(objId, fsButler, coaddType="deepCoadd"):
    """Show the inputs for the specified object Id, optionally at the specified position
    @param fsButler    Butler to provide inputs
    @param coaddType Type of coadd to examine
    """
    info = utils.makeMapperInfo(fsButler.butler)
    dataId = info.splitCoaddId(objId)
    dataId.pop('objId')
    src = fsButler.butler.get('deepCoadd_src', **dataId)
    src = src[objId == src.get("id")][0]
    pos = src.getCentroid()
    coadd = fsButler.butler.get(coaddType, **dataId)
    visitInputs = coadd.getInfo().getCoaddInputs().visits
    ccdInputs = coadd.getInfo().getCoaddInputs().ccds
    posSky = coadd.getWcs().pixelToSky(pos)

    psf = coadd.getPsf()
    sigmaCoadd = psf.computeShape(pos).getDeterminantRadius()

    print "%6s %3s %7s %5s %5s" % ("visit", "ccd", "exptime", "FWHM", "weight")

    totalExpTime = 0.0
    expTimeVisits = set()

    for i in range(len(ccdInputs)):
        input = ccdInputs[i]
        ccd = input.get("ccd")
        v = input.get("visit")
        bbox = input.getBBox()
        # It's quicker to not read all the pixels, so just read 1
        calexp = fsButler.butler.get("calexp_sub", bbox=afwGeom.BoxI(afwGeom.PointI(0, 0), afwGeom.ExtentI(1, 1)),
                            visit=int(v), ccd=ccd)
        calib = calexp.getCalib()
        psf = calexp.getPsf()
        pos = calexp.getWcs().skyToPixel(posSky)
        sigma = psf.computeShape(pos).getDeterminantRadius()
        exptime = calib.getExptime()
        weight = "%5.2f" % (input.get("weight"))
        if v not in expTimeVisits:
            totalExpTime += exptime
            expTimeVisits.add(v)
        print  "%6s %3s %7.0f %5.2f %5s" % (v, ccd, exptime, sigma, weight)
    print "Total Exposure time {0}".format(totalExpTime)
    print "Coadd FWHM {0}".format(sigmaCoadd)
