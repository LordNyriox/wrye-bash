# -*- coding: utf-8 -*-
#
# GPL License and Copyright Notice ============================================
#  This file is part of Wrye Bash.
#
#  Wrye Bash is free software: you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation, either version 3
#  of the License, or (at your option) any later version.
#
#  Wrye Bash is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Wrye Bash.  If not, see <https://www.gnu.org/licenses/>.
#
#  Wrye Bash copyright (C) 2005-2009 Wrye, 2010-2020 Wrye Bash Team
#  https://github.com/wrye-bash
#
# =============================================================================

"""This module contains oblivion multitweak item patcher classes that belong
to the Clothes Multitweaker - as well as the ClothesTweaker itself."""
import itertools
from ...patcher.base import AMultiTweaker, DynamicTweak
from ...patcher.patchers.base import MultiTweakItem
from ...patcher.patchers.base import MultiTweaker

# Patchers: 30 ----------------------------------------------------------------
class ClothesTweak(DynamicTweak, MultiTweakItem):
    tweak_read_classes = b'CLOT',
    clothes_flags = {
        u'hoods':    0x00000002,
        u'shirts':   0x00000004,
        u'pants':    0x00000008,
        u'gloves':   0x00000010,
        u'amulets':  0x00000100,
        u'rings2':   0x00010000,
        u'amulets2': 0x00020000,
        #--Multi
        u'robes':    0x0000000C, # (1<<2) | (1<<3),
        u'rings':    0x000000C0, # (1<<6) | (1<<7),
    }

    def __init__(self, tweak_name, tweak_tip, tweak_key, *tweak_choices):
        super(ClothesTweak, self).__init__(tweak_name, tweak_tip, tweak_key,
            *tweak_choices)
        type_key = tweak_key[:tweak_key.find(u'.')]
        self.or_type_flags = type_key in (u'robes', u'rings')
        self.type_flags = self.clothes_flags[type_key]

    @staticmethod
    def _get_biped_flags(record):
        """Returns the biped flags of the specified record as an integer."""
        return int(record.biped_flags) & 0xFFFF

    def wants_record(self, record):
        if self._is_nonplayable(record):
            return False
        rec_type_flags = self._get_biped_flags(record)
        my_type_flags = self.type_flags
        return ((rec_type_flags == my_type_flags) or (self.or_type_flags and (
                rec_type_flags & my_type_flags == rec_type_flags)))

#------------------------------------------------------------------------------
class ClothesTweak_MaxWeight(ClothesTweak):
    """Shared code of max weight tweaks."""
    tweak_log_msg = _(u'Clothes Reweighed: %(total_changed)d')

    @property
    def chosen_weight(self): return self.choiceValues[self.chosen][0]

    def wants_record(self, record):
        # Guess (i.e. super_weight) is intentionally overweight
        max_weight = self.chosen_weight
        super_weight = max(10, 5 * max_weight)
        return super(ClothesTweak_MaxWeight, self).wants_record(
            record) and max_weight < record.weight < super_weight

    def tweak_record(self, record):
        record.weight = self.chosen_weight

    def tweak_log(self, log, count):
        self.tweak_log_header = (self.tweak_name +
                                 u' [%4.2f]' % self.chosen_weight)
        super(ClothesTweak_MaxWeight, self).tweak_log(log, count)

#------------------------------------------------------------------------------
class _AUnblockTweak(ClothesTweak):
    """Unlimited rings, amulets."""
    tweak_log_msg = _(u'Clothes Tweaked: %(total_changed)d')

    @property
    def unblock_flags(self):
        try:
            return self._unblock_flags
        except AttributeError:
            self._unblock_flags = self.clothes_flags[
                self.tweak_key[self.tweak_key.rfind(u'.') + 1:]]
        return self._unblock_flags

    def wants_record(self, record):
        return super(_AUnblockTweak, self).wants_record(
            record) and int(self._get_biped_flags(record) & self.unblock_flags)

class ClothesTweak_Unblock(_AUnblockTweak, ClothesTweak):
    def tweak_record(self, record):
        record.biped_flags &= ~self.unblock_flags

#------------------------------------------------------------------------------
class _AClothesTweaker(AMultiTweaker):
    """Patches clothes in miscellaneous ways."""
    _read_write_records = (b'CLOT',)
    _unblock = ((_(u'Unlimited Amulets'),
                 _(u"Wear unlimited number of amulets - but they won't"
                   u'display.'),
                 u'amulets.unblock.amulets',),
                (_(u'Unlimited Rings'),
                 _(u"Wear unlimited number of rings - but they won't"
                   u'display.'),
                 u'rings.unblock.rings'),
                (_(u'Gloves Show Rings'),
                 _(u'Gloves will always show rings. (Conflicts with Unlimited '
                   u'Rings.)'),
                 u'gloves.unblock.rings2'),
                (_(u'Robes Show Pants'),
                _(u"Robes will allow pants, greaves, skirts - but they'll"
                  u'clip.'),
                u'robes.unblock.pants'),
                (_(u'Robes Show Amulets'),
                _(u'Robes will always show amulets. (Conflicts with Unlimited '
                  u'Amulets.)'),
                u'robes.show.amulets2'),)
    _max_weight = ((_(u'Max Weight Amulets'),
                    _(u'Amulet weight will be capped.'),
                    u'amulets.maxWeight',
                    (u'0.0', 0.0),
                    (u'0.1', 0.1),
                    (u'0.2', 0.2),
                    (u'0.5', 0.5),
                    (_(u'Custom'), 0.0),),
                   (_(u'Max Weight Rings'), _(u'Ring weight will be capped.'),
                    u'rings.maxWeight',
                    (u'0.0', 0.0),
                    (u'0.1', 0.1),
                    (u'0.2', 0.2),
                    (u'0.5', 0.5),
                    (_(u'Custom'), 0.0),),
                   (_(u'Max Weight Hoods'), _(u'Hood weight will be capped.'),
                    u'hoods.maxWeight',
                    (u'0.2', 0.2),
                    (u'0.5', 0.5),
                    (u'1.0', 1.0),
                    (_(u'Custom'), 0.0),),)
    scanOrder = 31
    editOrder = 31

class ClothesTweaker(_AClothesTweaker,MultiTweaker):
    @classmethod
    def tweak_instances(cls):
        return sorted(itertools.chain(
            (ClothesTweak_Unblock(*x) for x in cls._unblock),
            (ClothesTweak_MaxWeight(*x) for x in cls._max_weight)),
                      key=lambda a: a.tweak_name.lower())
