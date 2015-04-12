#    Copyright (C) 2015 Jeremy S. Sanders
#    Email: Jeremy Sanders <jeremy@jeremysanders.net>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License along
#    with this program; if not, write to the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
###############################################################################

from __future__ import division, print_function
import numpy as N

from ..compat import citems, czip
from .. import qtall as qt4
from .datasets import Dataset, DatasetBase, evalDatasetExpression, _

class DatasetFilterGenerator(object):
    """This object is shared by all DatasetFiltered datasets, to calculate
    the filter expression."""

    def __init__(self, inexpr, indatasets,
                 prefix="", suffix="",
                 invert=False, replaceblanks=False):
        """
        inexpr = filter expression
        indatasets = list of input datasets
        prefix = output prefix
        suffix = output suffix
        invert = invert filter
        replaceblanks = replace filtered values by nans
        """

        self.changeset = -1
        self.inexpr = inexpr
        self.indatasets = indatasets
        self.prefix = prefix
        self.suffix = suffix
        self.invert = invert
        self.replaceblanks = replaceblanks

        self.outdatasets = {}

    def filterNumeric(self, ds, filterarr):
        """Filter a numeric dataset."""
        outdata = {}
        minlen = len(filterarr)
        for attr in ds.columns:
            data = getattr(ds, attr)
            if data is None:
                filtered = None
            else:
                filtered = N.array(data[:minlen])
                if self.replaceblanks:
                    filtered[N.logical_not(filterarr)] = N.nan
                else:
                    filtered = filtered[filterarr]
            outdata[attr] = filtered
        return ds.returnCopyWithNewData(**outdata)

    def filterText(self, ds, filterarr):
        """Filter a text dataset."""
        if self.replaceblanks:
            filtered = [(d if f else "")
                        for f, d in czip(filterarr, data)]
        else:
            filtered = [d for f, d in czip(filterarr, data) if f]
        return ds.returnCopyWithNewData(data=filtered)

    def checkUpdate(self, doc):
        """Update filtering calculation if doc changed."""

        if doc.changeset == self.changeset:
            return
        self.changeset = doc.changeset

        # this is populated by output
        self.outdatasets = {}

        # evaluate filter expression
        d = evalDatasetExpression(doc, self.inexpr)
        if d is None:
            return
        if d.dimensions != 1:
            doc.log(
                _("Invalid number of dimensions in filter expression '%s'\n") %
                self.inexpr)
            return
        if d.datatype != "numeric":
            doc.log(
                _("Input filter expression non-numeric: '%s'\n") % self.inexpr)
            return

        filterarr = d.data.astype(N.bool)
        if self.invert:
            filterarr = N.logical_not(filterarr)

        # do filtering of datasets
        for name in self.indatasets:
            ds = doc.data.get(name)
            if ds is None or ds.dimensions != 1:
                doc.log(_("Filtered dataset '%s' has more than 1 dimension\n") %
                        name)
                continue
            minlen = min(len(ds.data), len(filterarr))
            filterarrchop = filterarr[:minlen]

            if ds.datatype == "numeric":
                filtered = self.filterNumeric(ds, filterarrchop)
            elif ds.datatype == "text":
                filtered = self.filterText(ds, filterarrchop)
            else:
                doc.log(_("Could not filter dataset '%s'\n") % name)
                continue

            self.outdatasets[name] = filtered

    def saveToFile(self, doc, fileobj):
        """Save datasets to file."""

        # find current datasets in document which use this generator
        # (some may have been deleted)
        names = []
        for name, ds in sorted(doc.data.items()):
            if getattr(ds, "generator", None) is self:
                names.append(ds.namein)

        args = [
            repr(self.inexpr),
            repr(names),
        ]
        if self.prefix:
            args.append("prefix="+repr(self.prefix))
        if self.suffix:
            args.append("suffix="+repr(self.suffix))
        if self.invert:
            args.append("invert=True")
        if self.replaceblanks:
            args.append("replaceblanks=True")

        fileobj.write("FilterDatasets(%s)\n" % ", ".join(args))

class DatasetFiltered(DatasetBase):
    """A dataset which is another dataset filtered by an expression."""

    dstype = "Filtered"
    dimensions = 1
    editable = False

    def __init__(self, gen, name, doc):
        DatasetBase.__init__(self)
        self.generator = gen
        self.namein = name
        self.document = doc
        self.changeset = -1
        self._internalds = None

    def _checkUpdate(self):
        """Recalculate if document has changed."""
        if self.document.changeset != self.changeset:
            self.generator.checkUpdate(self.document)
            self.changeset = self.document.changeset

            ds = self.generator.outdatasets.get(self.namein)
            if ds is None:
                self._internalds = Dataset(data=[])
            else:
                self._internalds = ds

    def linkedInformation(self):
        return _("Filtered '%s' using '%s'") % (
            self.namein, self.generator.inexpr)

    def saveToFile(self, fileobj, name, **args):
        """Save plugin to file, if this is the first one."""

        # Am I the first dataset in the document with this generator?
        am1st = False
        for ds in sorted(self.document.data):
            data = self.document.data[ds]
            if data is self:
                am1st = True
                break
            elif getattr(data, "generator", None) is self.generator:
                # not 1st
                break
        if am1st:
            self.generator.saveToFile(self.document, fileobj)

    def __getattr__(self, attr):
        """Lookup attribute from internal dataset."""
        self._checkUpdate()
        return getattr(self._internalds, attr)

class OperationDatasetsFilter(object):
    """Operation to filter datasets."""

    descr = _("filter datasets")

    def __init__(self, inexpr, indatasets,
                 prefix="", suffix="",
                 invert=False, replaceblanks=False):
        """Initialise operation:
        inexpr: input expression
        indatasets: list of dataset names
        prefix, suffix: output prefix/suffix
        invert: invert filter expression
        replaceblanks: replace output with blank/nan values.
        """

        if not prefix and not suffix:
            raise ValueError("Prefix and/or suffix must be given")
        self.inexpr = inexpr
        self.indatasets = indatasets
        self.prefix = prefix
        self.suffix = suffix
        self.invert = invert
        self.replaceblanks = replaceblanks

    def do(self, doc):
        """Do the operation."""

        gen = DatasetFilterGenerator(
            self.inexpr, self.indatasets,
            prefix=self.prefix, suffix=self.suffix,
            invert=self.invert, replaceblanks=self.replaceblanks)

        self.olddatasets = {}

        for name in self.indatasets:
            outname = self.prefix + name + self.suffix
            self.olddatasets[outname] = doc.data.get(outname)
            doc.setData(outname, DatasetFiltered(gen, name, doc))

        return gen.outdatasets

    def undo(self, doc):
        """Undo operation."""

        for name, val in citems(self.olddatasets):
            if val is None:
                doc.deleteData(name)
            else:
                doc.setData(name, val)
