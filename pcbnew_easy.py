# pcbnew_easy.py
# Wrapper API for more convenient/pythonic creation of PCB boards and modules.
# Probably this should better be integrated in the default API instead of as
# a wrapper. However this was the quickest way to improve the usability for
# myself.
#
# All values are in mm, and coordinates and sizes can be given as iterables
# (tuples, lists, numpy arrays, ...)
#
#  Copyright 2014 Piers Titus van der Torren <pierstitus@gmail.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#

import math
import cmath

import pcbnew

def inch_to_mm(val):
    """Convert from inch to mm

    Handles single values, sequences, sequences of sequences, etc.
    Also handles numpy arrays or any other object which can be multiplied with a float.
    """
    try:
        return val * 25.4
    except TypeError:
        return [inch_to_mm(v) for v in val]

def mm_to_inch(val):
    """Convert from mm to inch

    Handles single values, sequences, sequences of sequences, etc.
    Also handles numpy arrays or any other object which can be multiplied with a float.
    """
    try:
        return val / 25.4
    except TypeError:
        return [mm_to_inch(v) for v in val]

# unit helper functions
def _mm_to_iu(val):
    """Convert mm to internal units"""
    return pcbnew.FromMM(float(val))

def _mm_to_wxpoint(x, y):
    """Convert coordinate in mm to internal coordinate"""
    return pcbnew.wxPointMM(float(x), float(y))

def _mm_to_wxsize(x, y):
    """Convert size in mm to internal size"""
    return pcbnew.wxSizeMM(float(x), float(y))

def _iu_to_mm(wxobj):
    return pcbnew.ToMM(wxobj)

# unit conversion functions used in the classes below
_from_wxpoint = _iu_to_mm
_to_wxpoint = _mm_to_wxpoint

_from_wxsize = _iu_to_mm
_to_wxsize = _mm_to_wxsize

_from_iu = _iu_to_mm
_to_iu = _mm_to_iu

def _angle_to_iu(val):
    return val * 10.0

def _angle_from_iu(val):
    return val / 10.0

# if numpy is loaded, use numpy arrays for point and size tuples, to make
# calculations with points and sizes easier (e.g. module.position + (10,10))
# Don't use numpy if it's not loaded already to not force a depency on numpy.
# Another simple vector class might be better suited, but using a well known
# multidimensional array package has it's benefits too.
import sys
if 'numpy' in sys.modules:
    import numpy
    def _iu_to_mm_np(wxobj):
        return numpy.array(pcbnew.ToMM(wxobj))
    _from_wxpoint = _iu_to_mm_np
    _from_wxsize = _iu_to_mm_np


def rotate(coord, angle):
    """Rotate coordinate around (0, 0)"""
    coord = (coord[0]+coord[1]*1j) * cmath.exp(math.radians(angle)*1j)
    return (coord.real, coord.imag)

# dicts for converting layer name to id, used by _get_layer
layer_dict = {pcbnew.BOARD_GetStandardLayerName(n):n for n in range(pcbnew.LAYER_ID_COUNT)}
layer_names = {s:n for n, s in layer_dict.iteritems()}

def _get_layer(s):
    """Get layer id from layer name"""
    return layer_dict[s]

def _to_LayerSet(layers):
    """Create LayerSet used for defining pad layers"""
    bitset = 0
    for l in layers:
        bitset |= 1 << _get_layer(l)
    hexset = '{0:013x}'.format(bitset)
    lset = pcbnew.LSET()
    lset.ParseHex(hexset, len(hexset))
    return lset

def _from_LayerSet(layerset):
    mask = [c for c in layerset.FmtBin() if c in ('0','1')]
    mask.reverse()
    ids = [i for i, c in enumerate(mask) if c == '1']
    return tuple(layer_names[i] for i in ids)

class Board(object):
    def __init__(self, board=None):
        """Convenience wrapper for pcbnew Board"""
        if board == None:
            # if no board is given create a new board
            board = pcbnew.BOARD()
        self._board = board

    @property
    def modules(self):
        m = self._board.GetModules().begin()
        while not m == None:
            yield Module(m)
            m = m.Next()

    def save(self, filename=None):
        """Save the board to a file

        filename should have .kicad_pcb extention.
        """
        if filename == None:
            filename = self._board.GetFileName()
        self._board.Save(filename)

    def find_module(self, reference):
        """Find module with the given reference"""
        return Module(self._board.FindModuleByReference(reference))

    def create_module(self, reference, position=(0, 0)):
        """Create new module on the board"""
        module = pcbnew.MODULE(self._board)
        module.SetReference(reference)
        module.SetPosition(_to_wxpoint(position[0], position[1]))
        self._board.Add(module)
        return Module(module)

    def copy_module(self, original, reference, position=(0, 0)):
        """Create a copy of an existing module on the board"""
        module = pcbnew.MODULE(self._board)
        module.Copy(original._module)
        module.SetReference(reference)
        module.SetPosition(_to_wxpoint(position[0], position[1]))
        self._board.Add(module)
        return Module(module)

    def add_track_segment(self, start, end, layer='F.Cu', width=None):
        """Create a track segment"""
        if width == None:
            width = self._board.GetDesignSettings().GetCurrentTrackWidth()
        else:
            width = _to_iu(width)
        t = pcbnew.TRACK(self._board)
        t.SetWidth(width)
        t.SetLayer(_get_layer(layer))
        t.SetStart(_to_wxpoint(start[0], start[1]))
        t.SetEnd(_to_wxpoint(end[0], end[1]))
        self._board.Add(t)
        return t

    def add_track(self, coords, layer='F.Cu', width=None):
        """Create a track polyline

        Create track segments from each coordinate to the next.
        """
        for n in range(len(coords)-1):
            self.add_track_segment(coords[n], coords[n+1], layer=layer, width=width)

    def add_track_via(self, coord, layer_pair=('B.Cu', 'F.Cu'), size=None, drill=None):
        """Create a via on the board

        Args:
            coord: Position of the via
            layer_pair: Tuple of the connected layers (for example ('B.Cu', 'F.Cu'))
            size: size of via in mm, or None for current selection
            drill: size of drill in mm, or None for current selection
        """
        if size == None:
            size = self._board.GetDesignSettings().GetCurrentViaSize()
        else:
            size = _to_iu(size)
        if drill == None:
            drill = self._board.GetDesignSettings().GetCurrentViaDrill()
        else:
            drill = _to_iu(drill)
        via = pcbnew.VIA(self._board)
        #via.SetFlags( IS_NEW )
        #via.SetViaType( GetDesignSettings().m.CurrentViaType )
        via.SetWidth(size)
        #via.SetNetCode( GetBoard()->GetHighLightNetCode() )
        via.SetEnd(_to_wxpoint(coord[0], coord[1]))
        via.SetStart(_to_wxpoint(coord[0], coord[1]))

        via.SetLayerPair(_get_layer(layer_pair[0]), _get_layer(layer_pair[1]))
        via.SetDrill(drill)
        self._board.Add(via)
        return via

    def add_line(self, start, end, layer='F.SilkS', width=0.15):
        """Create a graphic line on the board"""
        a = pcbnew.DRAWSEGMENT(self._board)
        a.SetShape(pcbnew.S_SEGMENT)
        a.SetStart(_to_wxpoint(start[0], start[1]))
        a.SetEnd(_to_wxpoint(end[0], end[1]))
        a.SetLayer(_get_layer(layer))
        a.SetWidth(_to_iu(width))
        self._board.Add(a)
        return a

    def add_polyline(self, coords, layer='F.SilkS', width=0.15):
        """Create a graphic polyline on the board"""
        for n in range(len(coords)-1):
            self.add_line(coords[n], coords[n+1], layer=layer, width=width)

    def add_circle(self, center, radius, layer='F.SilkS', width=0.15):
        """Create a graphic circle on the board"""
        a = pcbnew.DRAWSEGMENT(self._board)
        a.SetShape(pcbnew.S_CIRCLE)
        a.SetCenter(_to_wxpoint(center[0], center[1]))
        start_coord = _to_wxpoint(center[0], center[1]+radius)
        a.SetArcStart(start_coord)
        a.SetLayer(_get_layer(layer))
        a.SetWidth(_to_iu(width))
        self._board.Add(a)
        return a

    def add_arc(self, center, radius, start_angle, stop_angle, layer='F.SilkS', width=0.15):
        """Create a graphic arc on the board"""
        start_coord = radius * cmath.exp(math.radians(start_angle-90)*1j)
        start_coord = _to_wxpoint(start_coord.real, start_coord.imag)
        angle = stop_angle - start_angle
        a = pcbnew.DRAWSEGMENT(self._board)
        a.SetShape(pcbnew.S_ARC)
        a.SetCenter(_to_wxpoint(center[0], center[1]))
        a.SetArcStart(start_coord)
        a.SetAngle(_angle_to_iu(angle))
        a.SetLayer(_get_layer(layer))
        a.SetWidth(_to_iu(width))
        self._board.Add(a)
        return a


class Module(object):
    def __init__(self, module):
        """Convenience wrapper for pcbnew Module"""
        self._module = module

    @property
    def position(self):
        return _from_wxpoint(self._module.GetPosition())
    @position.setter
    def position(self, position):
        self._module.SetPosition(_to_wxpoint(position[0], position[1]))

    @property
    def reference(self):
        return self._module.GetReference()
    @reference.setter
    def reference(self, value):
        self._module.SetReference(value)

    @property
    def value(self):
        return self._module.GetValue()
    @value.setter
    def value(self, value):
        self._module.SetValue(value)

    @property
    def orientation(self):
        return _angle_from_iu(self._module.GetOrientation())
    @orientation.setter
    def orientation(self, value):
        self._module.SetOrientation(_angle_to_iu(value))

    @property
    def pads(self):
        p = self._module.Pads().begin()
        while not p == None:
            yield Pad(p)
            p = p.Next()

    def delete(self):
        """Delete module from board"""
        self._module.GetBoard().Delete(self._module)
        self._module = None

    def flip(self, center=None):
        """Flip module

        If center is given flip w.r.t. that coordinate.
        """
        if center==None:
            center = self.position
        self._module.Flip(_to_wxpoint(center[0], center[1]))

    def add_line(self, start, end, layer='F.SilkS', width=0.15):
        """Create a graphic line on the module"""
        a = pcbnew.EDGE_MODULE(self._module)
        a.SetShape(pcbnew.S_SEGMENT)
        a.SetStart(_to_wxpoint(start[0], start[1]))
        a.SetEnd(_to_wxpoint(end[0], end[1]))
        a.SetLayer(_get_layer(layer))
        a.SetWidth(_to_iu(width))
        a.SetLocalCoord()
        self._module.Add(a)
        return a

    def add_polyline(self, coords, layer='F.SilkS', width=0.15):
        """Create a graphic polyline on the module"""
        for n in range(len(coords)-1):
            self.add_line(coords[n], coords[n+1], layer=layer, width=width)

    def add_circle(self, center, radius, layer='F.SilkS', width=0.15):
        """Create a graphic circle on the module"""
        a = pcbnew.EDGE_MODULE(self._module)
        a.SetShape(pcbnew.S_CIRCLE)
        a.SetCenter(_to_wxpoint(center[0], center[1]))
        start_coord = _to_wxpoint(center[0], center[1]+radius)
        a.SetArcStart(start_coord)
        a.SetLayer(_get_layer(layer))
        a.SetWidth(_to_iu(width))
        a.SetLocalCoord()
        self._module.Add(a)
        return a

    def add_arc(self, center, radius, start_angle, stop_angle, layer='F.SilkS', width=0.15):
        """Create a graphic arc on the module"""
        start_coord = radius * cmath.exp(math.radians(start_angle-90)*1j)
        start_coord = _to_wxpoint(start_coord.real, start_coord.imag)
        angle = stop_angle - start_angle
        a = pcbnew.EDGE_MODULE(self._module)
        a.SetShape(pcbnew.S_ARC)
        a.SetCenter(_to_wxpoint(center[0], center[1]))
        a.SetArcStart(start_coord)
        a.SetAngle(_angle_to_iu(angle))
        a.SetLayer(_get_layer(layer))
        a.SetWidth(_to_iu(width))
        a.SetLocalCoord()
        self._module.Add(a)
        return a

    def add_pad(self, position, size, name='', pad_type='standard', shape='circle',
                drill=1.0, layers=None):
        """Create a pad on the module

        Args:
            position: pad position in mm
            size: pad size in mm, value if shape == 'circle', tuple otherwise
            name: pad name/number
            pad_type: One of 'standard', 'smd', 'conn', 'hole_not_plated'
            shape: One of 'circle', 'rect', 'oval', 'trapezoid'
            drill: drill size in mm, single value for round hole, or tuple for oblong hole.
            layers: None for default, or a list of layer definitions (for example: ['F.Cu', 'F.Mask'])
        """
        pad = Pad(pcbnew.D_PAD(self._module))

        pad.type = pad_type
        pad.shape = shape
        pad.size = size
        pad.name = name
        pad.position = position
        pad.layers = layers
        pad.drill = drill

        self._module.Add(pad._pad)
        return pad

    def save(self, library_path):
        """Save footprint in given library

        library_path should end with .pretty
        """
        self._module.SetFPID(pcbnew.FPID(self._module.GetReference()))

        io = pcbnew.PCB_IO()

        try:
            io.FootprintLibCreate(library_path)
        except IOError:
            pass # we try to create, but may be it exists already

        io.FootprintSave(library_path, self._module)

class Pad(object):
    """Convenience wrapper for pcbnew Pad"""
    _pad_types = {'standard':pcbnew.PAD_STANDARD,
                  'smd':pcbnew.PAD_SMD,
                  'conn':pcbnew.PAD_CONN,
                  'hole_not_plated':pcbnew.PAD_HOLE_NOT_PLATED}
    _pad_types_id = {s:n for n, s in _pad_types.iteritems()}
    _shapes = {'circle':pcbnew.PAD_CIRCLE,
               'rect':pcbnew.PAD_RECT,
               'oval':pcbnew.PAD_OVAL,
               'trapezoid':pcbnew.PAD_TRAPEZOID}
    _shapes_id = {s:n for n, s in _shapes.iteritems()}

    def __init__(self, pad):
        self._pad = pad

    @property
    def position(self):
        return _from_wxpoint(self._pad.GetPosition())
    @position.setter
    def position(self, position):
        self._pad.SetPosition(_to_wxpoint(position[0], position[1]))
        self._pad.SetLocalCoord()

    @property
    def name(self):
        return self._pad.GetPadName()
    @name.setter
    def name(self, value):
        self._pad.SetPadName(value)

    @property
    def type(self):
        return self._pad_types_id[self._pad.GetAttribute()]
    @type.setter
    def type(self, value):
        self._pad.SetAttribute(self._pad_types[value])

    @property
    def shape(self):
        return self._shapes_id[self._pad.GetShape()]
    @shape.setter
    def shape(self, value):
        self._pad.SetShape(self._shapes[value])

    @property
    def size(self):
        if self.shape == 'circle':
            return _from_wxsize(self._pad.GetSize())[0]
        else:
            return _from_wxsize(self._pad.GetSize())
    @size.setter
    def size(self, size):
        if self.shape == 'circle':
            self._pad.SetSize(_to_wxsize(size, size))
        else:
            self._pad.SetSize(_to_wxsize(size[0], size[1]))

    @property
    def orientation(self):
        return _angle_from_iu(self._pad.GetOrientation())
    @orientation.setter
    def orientation(self, value):
        self._pad.SetOrientation(_angle_to_iu(value))

    @property
    def layers(self):
        return _from_LayerSet(self._pad.GetLayerSet())
    @layers.setter
    def layers(self, value):
        if value == None: # if None set default layers
            default_masks = {'standard':self._pad.StandardMask(),
                             'smd':self._pad.SMDMask(),
                             'conn':self._pad.ConnSMDMask(),
                             'hole_not_plated':self._pad.UnplatedHoleMask()}
            self._pad.SetLayerSet(default_masks[self.type])
        else:
            self._pad.SetLayerSet(_to_LayerSet(value))

    @property
    def drill(self):
        if self.type in ('standard', 'hole_not_plated'):
            if self._pad.GetDrillShape() == pcbnew.PAD_DRILL_OBLONG:
                return _from_wxsize(self._pad.GetDrillSize())
            else:
                return _from_wxsize(self._pad.GetDrillSize())[0]
        else:
            return None
    @drill.setter
    def drill(self, drill):
        if self.type in ('standard', 'hole_not_plated'):
            if hasattr(drill, '__getitem__'):
                self._pad.SetDrillShape(pcbnew.PAD_DRILL_OBLONG)
                self._pad.SetDrillSize(_to_wxsize(drill[0], drill[1]))
            else:
                self._pad.SetDrillSize(_to_wxsize(drill, drill))
        else:
            pass

    def delete(self):
        """Delete pad from module"""
        self._pad.GetParent().DeleteChild(self._pad)
        self._pad = None

def get_board():
    """Get the current board"""
    return Board(pcbnew.GetBoard())


# Usage example and test
def test():
    """Make an example board

    Run in the pcbnew scripting console:
      import pcbnew_easy
      pcbnew_easy.test()
    """
    # get current board
    pcb = get_board()

    # create test module
    m = pcb.create_module('test')
    m.add_arc(center=(0, 0), radius=8, start_angle=-90, stop_angle=90, width=0.2)
    m.add_line(start=(-8, 0), end=(8, 0), width=0.2)
    m.add_pad(position=(-4, -3), size=2, drill=1)
    m.add_pad(position=(4, -3), size=2, drill=1, layers=['B.Cu', 'F.Cu'])
    for n, x in enumerate([-1, -.5, 0, .5, 1]):
        m.add_pad(position=(x, -4), size=(0.25, 1.2), name=n, pad_type='smd', shape='rect')

    # move module to right location
    m.position = (30, 30)

    # add test track with via
    track1 = [(30, 26), (30, 50), (60, 80)]
    track2 = [(60, 80), (80, 80)]
    pcb.add_track(track1, layer='F.Cu', width=0.25)
    pcb.add_track_via(track1[-1])
    pcb.add_track(track2, layer='B.Cu')

    # add board edge
    ul = (20, 20)
    pcb_size = (100, 80)
    edge = [ul,
            (ul[0], ul[1]+pcb_size[1]),
            (ul[0]+pcb_size[0], ul[1]+pcb_size[1]),
            (ul[0]+pcb_size[0], ul[1]),
            ul]
    pcb.add_polyline(edge, layer='Edge.Cuts')

    print('List all pads of all modules')
    for module in pcb.modules:
        print(module.reference)
        for pad in m.pads:
            print('  {0.name}: {0.shape}'.format(pad))
