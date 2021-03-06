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
to the Gmst Multitweaker - as well as the GmstTweaker itself. Gmst stands
for game settings."""
from __future__ import print_function
from ... import bush # for game
from ...bolt import floats_equal
from ...patcher.base import DynamicTweak
from ...patcher.patchers.base import MultiTweakItem
from ...patcher.patchers.base import MultiTweaker

# Patchers: 30 ----------------------------------------------------------------
class GlobalsTweak(DynamicTweak, MultiTweakItem):
    """Sets a global to specified value."""
    tweak_read_classes = b'GLOB',
    show_key_for_custom = True

    @property
    def chosen_value(self):
        # Globals are always stored as floats, regardless of what the CS says
        return float(self.choiceValues[self.chosen][0])

    def wants_record(self, record):
        return (getattr(record, u'eid', None) and # skip missing and empty EDID
                record.eid.lower() == self.tweak_key and
                record.global_value != self.chosen_value)

    def tweak_record(self, record):
        record.global_value = self.chosen_value

    def tweak_log(self, log, count):
        if count: log(u'* ' + _(u'%s set to: %4.2f') % (
            self.tweak_name, self.chosen_value))

#------------------------------------------------------------------------------
class GmstTweak(DynamicTweak, MultiTweakItem):
    """Sets a GMST to specified value."""
    tweak_read_classes = b'GMST',
    show_key_for_custom = True

    @property
    def chosen_eids(self):
        return ((self.tweak_key,), self.tweak_key)[isinstance(self.tweak_key,
                                                              tuple)]

    @property
    def chosen_values(self): return self.choiceValues[self.chosen]

    @property
    def eid_was_itpo(self):
        try:
            return self._eid_was_itpo
        except AttributeError:
            self._eid_was_itpo = {e.lower(): False for e in self.chosen_eids}
            return self._eid_was_itpo

    def _find_chosen_value(self, wanted_eid):
        """Returns the value the user chose for the game setting with the
        specified editor ID. Note that wanted_eid must be lower-case!"""
        for test_eid, test_val in zip(self.chosen_eids, self.chosen_values):
            if wanted_eid == test_eid.lower():
                return test_val
        return None

    def _find_original_eid(self, lower_eid):
        """We need to find the original case of the EDID, otherwise getFMSTFid
        blows - plus the dumped record will look nicer :)."""
        for orig_eid in self.chosen_eids:
            if lower_eid == orig_eid.lower():
                return orig_eid
        return lower_eid # fallback, should never happen

    def validate_values(self, chosen_values):
        if bush.game.fsName == u'Oblivion': ##: add a comment why TES4 only!
            for target_value in chosen_values:
                if target_value < 0:
                    return _(u"Oblivion GMST values can't be negative")
        for target_eid, target_value in zip(self.chosen_eids, chosen_values):
            if target_eid.startswith(u'f') and type(target_value) != float:
                    return _(u"The value chosen for GMST '%s' must be a "
                             u'float, but is currently of type %s (%s).') % (
                        target_eid, type(target_value).__name__, target_value)
        return None

    def wants_record(self, record):
        if record.fid[0] not in bush.game.bethDataFiles:
            return False # Avoid adding new masters just for a game setting
        rec_eid = record.eid.lower()
        if rec_eid not in self.eid_was_itpo: return False # not needed
        target_val = self._find_chosen_value(rec_eid)
        if rec_eid.startswith(u'f'):
            ret_val = not floats_equal(record.value, target_val)
        else:
            ret_val = record.value != target_val
        # Remember whether the last entry was ITPO or not
        self.eid_was_itpo[rec_eid] = not ret_val
        return ret_val

    def tweak_record(self, record):
        rec_eid = record.eid.lower()
        # We don't need to create a GMST for this EDID anymore
        self.eid_was_itpo[rec_eid] = True
        record.value = self._find_chosen_value(rec_eid)

    def tweak_log(self, log, count): # count is ignored here
        if len(self.choiceLabels) > 1:
            if self.choiceLabels[self.chosen].startswith(_(u'Custom')):
                if isinstance(self.chosen_values[0], basestring):
                    log(u'* %s: %s %s' % (
                        self.tweak_name, self.choiceLabels[self.chosen],
                        self.chosen_values[0]))
                else:
                    log(u'* %s: %s %4.2f' % (
                        self.tweak_name, self.choiceLabels[self.chosen],
                        self.chosen_values[0]))
            else:
                log(u'* %s: %s' % (
                    self.tweak_name, self.choiceLabels[self.chosen]))
        else:
            log(u'* ' + self.tweak_name)

    def finish_tweaking(self, patch_file):
        # Create new records for any remaining EDIDs
        for remaining_eid, was_itpo in self.eid_was_itpo.iteritems():
            if not was_itpo:
                patch_file.new_gmst(self._find_original_eid(remaining_eid),
                    self._find_chosen_value(remaining_eid))

#------------------------------------------------------------------------------
class GmstTweaker(MultiTweaker):
    """Tweaks GMST records in various ways."""
    scanOrder = 29
    editOrder = 29
    _class_tweaks = [(GlobalsTweak, bush.game.GlobalsTweaks),
                     (GmstTweak, bush.game.GmstTweaks)]

    @classmethod
    def tweak_instances(cls):
        instances = []
        for clazz, game_tweaks in cls._class_tweaks:
            for tweak in game_tweaks:
                if isinstance(tweak, tuple):
                    new_tweak = clazz(*tweak)
                elif isinstance(tweak, list):
                    new_tweak = clazz(*tweak[0])
                    new_tweak.default_enabled = tweak[1].get(
                        u'default_enabled', False)
                else:
                    raise SyntaxError(u'Invalid GMST tweak syntax: tuple or '
                                      u'list expected, got %r' % type(tweak))
                instances.append(new_tweak)
        instances.sort(key=lambda a: a.tweak_name.lower())
        return instances
