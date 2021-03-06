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

"""Patch dialog"""
import StringIO
import copy
import errno
import re
import time
from datetime import timedelta
from . import BashFrame ##: drop this - decouple !
from .. import balt, bass, bolt, bosh, bush, env, load_order
from ..balt import Link, Resources
from ..bolt import SubProgress, GPath, Path
from ..exception import BoltError, CancelError, FileEditError, \
    PluginsFullError, SkipError
from ..gui import CancelButton, DeselectAllButton, HLayout, Label, \
    LayoutOptions, OkButton, OpenButton, RevertButton, RevertToSavedButton, \
    SaveAsButton, SelectAllButton, Stretch, VLayout, DialogWindow, \
    CheckListBox, HorizontalLine
from ..patcher import configIsCBash, exportConfig, list_patches_dir
from ..patcher.patch_files import PatchFile

# Final lists of gui patcher classes instances, initialized in
# gui_patchers.InitPatchers() based on game. These must be copied as needed.
all_gui_patchers = [] #--All gui patchers classes for this game

class PatchDialog(DialogWindow):
    """Bash Patch update dialog.

    :type _gui_patchers: list[basher.gui_patchers._PatcherPanel]
    """
    _min_size = (400, 300)

    def __init__(self, parent, patchInfo, mods_to_reselect):
        self.mods_to_reselect = mods_to_reselect
        self.parent = parent
        title = _(u'Update ') + patchInfo.name.s
        size = balt.sizes.get(self.__class__.__name__, (500,600))
        super(PatchDialog, self).__init__(parent, title=title,
            icon_bundle=Resources.bashMonkey, sizes_dict=balt.sizes, size=size)
        #--Data
        list_patches_dir() # refresh cached dir
        groupOrder = dict([(group,index) for index,group in
            enumerate((_(u'General'),_(u'Importers'),_(u'Tweakers'),_(u'Special')))])
        patchConfigs = bosh.modInfos.table.getItem(patchInfo.name,'bash.patch.configs',{})
        if configIsCBash(patchConfigs):
            patchConfigs = {}
        isFirstLoad = 0 == len(patchConfigs)
        self.patchInfo = patchInfo
        self._gui_patchers = [copy.deepcopy(p) for p in all_gui_patchers]
        self._gui_patchers.sort(key=lambda a: a.__class__.patcher_name)
        self._gui_patchers.sort(key=lambda a: groupOrder[a.patcher_type.group]) ##: what does this ordering do??
        for patcher in self._gui_patchers:
            patcher.getConfig(patchConfigs) #--Will set patcher.isEnabled
            patcher.SetIsFirstLoad(isFirstLoad)
        self.currentPatcher = None
        patcherNames = [patcher.patcher_name for patcher in self._gui_patchers]
        #--GUI elements
        self.gExecute = OkButton(self, btn_label=_(u'Build Patch'))
        self.gExecute.on_clicked.subscribe(self.PatchExecute)
        # TODO(nycz): somehow move setUAC further into env?
        # Note: for this to work correctly, it needs to be run BEFORE
        # appending a menu item to a menu (and so, needs to be enabled/
        # disabled prior to that as well.
        # TODO(nycz): DEWX - Button.GetHandle
        env.setUAC(self.gExecute._native_widget.GetHandle(), True)
        self.gSelectAll = SelectAllButton(self)
        self.gSelectAll.on_clicked.subscribe(
            lambda: self.mass_select_recursive(True))
        self.gDeselectAll = DeselectAllButton(self)
        self.gDeselectAll.on_clicked.subscribe(
            lambda: self.mass_select_recursive(False))
        cancelButton = CancelButton(self)
        self.gPatchers = CheckListBox(self, choices=patcherNames,
                                      isSingle=True, onSelect=self.OnSelect,
                                      onCheck=self.OnCheck)
        self.gExportConfig = SaveAsButton(self, btn_label=_(u'Export'))
        self.gExportConfig.on_clicked.subscribe(self.ExportConfig)
        self.gImportConfig = OpenButton(self, btn_label=_(u'Import'))
        self.gImportConfig.on_clicked.subscribe(self.ImportConfig)
        self.gRevertConfig = RevertToSavedButton(self)
        self.gRevertConfig.on_clicked.subscribe(self.RevertConfig)
        self.gRevertToDefault = RevertButton(self,
                                             btn_label=_(u'Revert To Default'))
        self.gRevertToDefault.on_clicked.subscribe(self.DefaultConfig)
        for index,patcher in enumerate(self._gui_patchers):
            self.gPatchers.lb_check_at_index(index, patcher.isEnabled)
        self.defaultTipText = _(u'Items that are new since the last time this patch was built are displayed in bold')
        self.gTipText = Label(self,self.defaultTipText)
        #--Events
        self.gPatchers.on_mouse_leaving.subscribe(self._mouse_leaving)
        self.gPatchers.on_mouse_motion.subscribe(self.handle_mouse_motion)
        self.gPatchers.on_key_pressed.subscribe(self._on_char)
        self.mouse_dex = -1
        #--Layout
        self.config_layout = VLayout(item_expand=True, item_weight=1)
        VLayout(border=4, spacing=4, item_expand=True, items=[
            (HLayout(spacing=8, item_expand=True, items=[
                self.gPatchers,
                (self.config_layout, LayoutOptions(weight=1))
             ]), LayoutOptions(weight=1)),
            self.gTipText,
            HorizontalLine(self),
            HLayout(spacing=4, items=[
                Stretch(), self.gExportConfig, self.gImportConfig,
                self.gRevertConfig, self.gRevertToDefault]),
            HLayout(spacing=4, items=[
                Stretch(), self.gExecute, self.gSelectAll, self.gDeselectAll,
                cancelButton])
        ]).apply_to(self)
        #--Patcher panels
        for patcher in self._gui_patchers:
            patcher.GetConfigPanel(self, self.config_layout,
                                   self.gTipText).pnl_hide()
        initial_select = min(len(self._gui_patchers) - 1, 1)
        if initial_select >= 0:
            self.gPatchers.lb_select_index(initial_select) # callback not fired
            self.ShowPatcher(self._gui_patchers[initial_select]) # so this is needed
        self.SetOkEnable()

    #--Core -------------------------------
    def SetOkEnable(self):
        """Enable Build Patch button if at least one patcher is enabled."""
        self.gExecute.enabled = any(p.isEnabled for p in self._gui_patchers)

    def ShowPatcher(self,patcher):
        """Show patcher panel."""
        if patcher == self.currentPatcher: return
        if self.currentPatcher is not None:
            self.currentPatcher.gConfigPanel.pnl_hide()
        patcher.GetConfigPanel(self, self.config_layout, self.gTipText).visible = True
        self._native_widget.Layout()
        patcher.Layout()
        self.currentPatcher = patcher

    @balt.conversation
    def PatchExecute(self): # TODO(ut): needs more work to reduce P/C differences to an absolute minimum
        """Do the patch."""
        self.accept_modal()
        patchFile = progress = None
        try:
            patch_name = self.patchInfo.name
            patch_size = self.patchInfo.size
            progress = balt.Progress(patch_name.s,(u' '*60+u'\n'), abort=True)
            timer1 = time.clock()
            #--Save configs
            self._saveConfig(patch_name)
            #--Do it
            log = bolt.LogFile(StringIO.StringIO())
            patchFile = PatchFile(self.patchInfo)
            enabled_patchers = [p.get_patcher_instance(patchFile) for p in
                                self._gui_patchers if p.isEnabled] ##: what happens if empty
            patchFile.init_patchers_data(enabled_patchers, SubProgress(progress, 0, 0.1)) #try to speed this up!
            patchFile.initFactories(SubProgress(progress,0.1,0.2)) #no speeding needed/really possible (less than 1/4 second even with large LO)
            patchFile.scanLoadMods(SubProgress(progress,0.2,0.8)) #try to speed this up!
            patchFile.buildPatch(log,SubProgress(progress,0.8,0.9))#no speeding needed/really possible (less than 1/4 second even with large LO)
            if len(patchFile.tes4.masters) > 255:
                balt.showError(self,
                    _(u'The resulting Bashed Patch contains too many '
                      u'masters (>255). You can try to disable some '
                      u'patchers, create a second Bashed Patch and '
                      u'rebuild that one with only the patchers you '
                      u'disabled in this one active.'))
                return # Abort, we'll just blow up on saving it
            #--Save
            progress.setCancel(False, patch_name.s+u'\n'+_(u'Saving...'))
            progress(0.9)
            self._save_pbash(patchFile, patch_name)
            #--Done
            progress.Destroy(); progress = None
            timer2 = time.clock()
            #--Readme and log
            log.setHeader(None)
            log(u'{{CSS:wtxt_sand_small.css}}')
            logValue = log.out.getvalue()
            log.out.close()
            timerString = unicode(timedelta(seconds=round(timer2 - timer1, 3))).rstrip(u'0')
            logValue = re.sub(u'TIMEPLACEHOLDER', timerString, logValue, 1)
            readme = bosh.modInfos.store_dir.join(u'Docs', patch_name.sroot + u'.txt')
            docsDir = bass.settings.get('balt.WryeLog.cssDir', GPath(u''))
            tempReadmeDir = Path.tempDir().join(u'Docs')
            tempReadme = tempReadmeDir.join(patch_name.sroot+u'.txt')
            #--Write log/readme to temp dir first
            with tempReadme.open('w',encoding='utf-8-sig') as file:
                file.write(logValue)
            #--Convert log/readmeto wtxt
            bolt.WryeText.genHtml(tempReadme,None,docsDir)
            #--Try moving temp log/readme to Docs dir
            try:
                env.shellMove(tempReadmeDir, bass.dirs[u'mods'],
                              parent=self._native_widget)
            except (CancelError,SkipError):
                # User didn't allow UAC, move to My Games directory instead
                env.shellMove([tempReadme, tempReadme.root + u'.html'],
                              bass.dirs[u'saveBase'], parent=self)
                readme = bass.dirs[u'saveBase'].join(readme.tail)
            #finally:
            #    tempReadmeDir.head.rmtree(safety=tempReadmeDir.head.stail)
            readme = readme.root + u'.html'
            bosh.modInfos.table.setItem(patch_name, 'doc', readme)
            balt.playSound(self.parent, bass.inisettings['SoundSuccess'].s)
            balt.WryeLog(self.parent, readme, patch_name.s,
                         log_icons=Resources.bashBlue)
            #--Select?
            if self.mods_to_reselect:
                for mod in self.mods_to_reselect:
                    bosh.modInfos.lo_activate(mod, doSave=False)
                self.mods_to_reselect.clear()
                bosh.modInfos.cached_lo_save_active() ##: also done below duh
            count, message = 0, _(u'Activate %s?') % patch_name.s
            if load_order.cached_is_active(patch_name) or (
                        bass.inisettings['PromptActivateBashedPatch'] and
                        balt.askYes(self.parent, message, patch_name.s)):
                try:
                    changedFiles = bosh.modInfos.lo_activate(patch_name,
                                                             doSave=True)
                    count = len(changedFiles)
                    if count > 1: Link.Frame.set_status_info(
                            _(u'Masters Activated: ') + unicode(count - 1))
                except PluginsFullError:
                    balt.showError(self, _(
                        u'Unable to add mod %s because load list is full.')
                                   % patch_name.s)
            # although improbable user has package with bashed patches...
            info = bosh.modInfos.new_info(patch_name, notify_bain=True)
            if info.size == patch_size:
                # needed if size remains the same - mtime is set in
                # parsers.ModFile#safeSave which can't use
                # setmtime(crc_changed), as no info is there. In this case
                # _reset_cache > calculate_crc() would not detect the crc
                # change. That's a general problem with crc cache - API limits
                info.calculate_crc(recalculate=True)
            BashFrame.modList.RefreshUI(refreshSaves=bool(count))
        except CancelError:
            pass
        except FileEditError as error:
            balt.playSound(self.parent, bass.inisettings['SoundError'].s)
            balt.showError(self,u'%s'%error,_(u'File Edit Error'))
            bolt.deprint(u'Exception during Bashed Patch building:',
                traceback=True)
        except BoltError as error:
            balt.playSound(self.parent, bass.inisettings['SoundError'].s)
            balt.showError(self,u'%s'%error,_(u'Processing Error'))
            bolt.deprint(u'Exception during Bashed Patch building:',
                traceback=True)
        except:
            balt.playSound(self.parent, bass.inisettings['SoundError'].s)
            bolt.deprint(u'Exception during Bashed Patch building:',
                traceback=True)
            raise
        finally:
            if progress: progress.Destroy()

    def _save_pbash(self, patchFile, patch_name):
        while True:
            try:
                # FIXME will keep displaying a bogus UAC prompt if file is
                # locked - aborting bogus UAC dialog raises SkipError() in
                # shellMove, not sure if ever a Windows or Cancel are raised
                patchFile.safeSave()
                return
            except (CancelError, SkipError, OSError, IOError) as werr:
                if isinstance(werr, OSError) and werr.errno != errno.EACCES:
                    raise
                if self._pretry(patch_name):
                    continue
                raise # will raise the SkipError which is correctly processed

    ##: Ugly warts below (see also FIXME above)
    def _pretry(self, patch_name):
        return balt.askYes(
            self, (_(u'Bash encountered an error when saving '
                     u'%(patch_name)s.') + u'\n\n' +
                   _(u'Either Bash needs Administrator Privileges to save '
                     u'the file, or the file is in use by another process '
                     u'such as %(xedit_name)s.') + u'\n' +
                   _(u'Please close any program that is accessing '
                     u'%(patch_name)s, and provide Administrator Privileges '
                     u'if prompted to do so.') + u'\n\n' +
                   _(u'Try again?')) % {
                u'patch_name': patch_name.s,
                u'xedit_name': bush.game.Xe.full_name},
            _(u'Bashed Patch - Save Error'))

    def __config(self):
        config = {'ImportedMods': set()}
        for p in self._gui_patchers: p.saveConfig(config)
        return config

    def _saveConfig(self, patch_name):
        """Save the configuration"""
        config = self.__config()
        bosh.modInfos.table.setItem(patch_name, 'bash.patch.configs', config)

    def ExportConfig(self):
        """Export the configuration to a user selected dat file."""
        config = self.__config()
        exportConfig(patch_name=self.patchInfo.name, config=config,
            win=self.parent, outDir=bass.dirs[u'patches'])

    __old_key = GPath(u'Saved Bashed Patch Configuration')
    __new_key = u'Saved Bashed Patch Configuration (%s)'
    def ImportConfig(self):
        """Import the configuration from a user selected dat file."""
        config_dat = self.patchInfo.name + u'_Configuration.dat'
        textDir = bass.dirs[u'patches']
        textDir.makedirs()
        #--File dialog
        textPath = balt.askOpen(self.parent,
                                _(u'Import Bashed Patch configuration from:'),
                                textDir, config_dat, u'*.dat', mustExist=True)
        if not textPath: return
        table = bolt.DataTable(bolt.PickleDict(textPath))
        # try the current Bashed Patch mode.
        patchConfigs = table.getItem(GPath(self.__new_key % u'Python'),
            'bash.patch.configs', {})
        convert = False
        if not patchConfigs: # try the non-current Bashed Patch mode
            patchConfigs = table.getItem(GPath(self.__new_key % u'CBash'),
                'bash.patch.configs', {})
            convert = bool(patchConfigs)
        if not patchConfigs: # try the old format
            patchConfigs = table.getItem(self.__old_key, 'bash.patch.configs',
                {})
            convert = bool(patchConfigs)
        if not patchConfigs:
            balt.showWarning(self,
                _(u'No patch config data found in %s') % textPath,
                title=_(u'Import Config'))
            return
        if convert:
            balt.showError(self,
                _(u'The patch config data in %s is too old for this version '
                  u'of Wrye Bash to handle or was created with CBash. Please '
                  u'use Wrye Bash 307 to import the config, then rebuild the '
                  u'patch using PBash to convert it and finally export the '
                  u'config again to get one that will work in this '
                  u'version.') % textPath, title=_(u'Config Too Old'))
            return
        self._load_config(patchConfigs)

    def _load_config(self, patchConfigs, set_first_load=False, default=False):
        for index, patcher in enumerate(self._gui_patchers):
            patcher.import_config(patchConfigs, set_first_load=set_first_load,
                                  default=default)
            self.gPatchers.lb_check_at_index(index, patcher.isEnabled)
        self.SetOkEnable()

    def RevertConfig(self):
        """Revert configuration back to saved"""
        patchConfigs = bosh.modInfos.table.getItem(self.patchInfo.name,
                                                   'bash.patch.configs', {})
        self._load_config(patchConfigs)

    def DefaultConfig(self):
        """Revert configuration back to default"""
        self._load_config({}, set_first_load=True, default=True)

    def mass_select_recursive(self, select=True):
        """Select or deselect all patchers and entries in patchers with child
        entries."""
        self.gPatchers.set_all_checkmarks(checked=select)
        for patcher in self._gui_patchers:
            patcher.mass_select(select=select)
        self.gExecute.enabled = select

    #--GUI --------------------------------
    def OnSelect(self, lb_selection_dex, _lb_selection_str):
        """Responds to patchers list selection."""
        self.ShowPatcher(self._gui_patchers[lb_selection_dex])
        self.gPatchers.lb_select_index(lb_selection_dex)

    def CheckPatcher(self, patcher):
        """Enable a patcher - Called from a patcher's OnCheck method."""
        index = self._gui_patchers.index(patcher)
        self.gPatchers.lb_check_at_index(index, True)
        self.SetOkEnable()

    def BoldPatcher(self, patcher):
        """Set the patcher label to bold font.  Called from a patcher when
        it realizes it has something new in its list"""
        index = self._gui_patchers.index(patcher)
        self.gPatchers.lb_bold_font_at_index(index)

    def OnCheck(self, lb_selection_dex):
        """Toggle patcher activity state."""
        patcher = self._gui_patchers[lb_selection_dex]
        patcher.isEnabled = self.gPatchers.lb_is_checked_at_index(lb_selection_dex)
        self.gPatchers.lb_select_index(lb_selection_dex)
        self.ShowPatcher(patcher) # SetSelection does not fire the callback
        self.SetOkEnable()

    def _mouse_leaving(self): self._set_tip_text(-1)

    def handle_mouse_motion(self, wrapped_evt, lb_dex):
        """Show tip text when changing item."""
        if wrapped_evt.is_moving:
            if lb_dex != self.mouse_dex:
                self.mouse_dex = lb_dex
        self._set_tip_text(lb_dex)

    def _set_tip_text(self, mouseItem):
        if 0 <= mouseItem < len(self._gui_patchers):
            gui_patcher = self._gui_patchers[mouseItem]
            self.gTipText.label_text = gui_patcher.patcher_tip
        else:
            self.gTipText.label_text = self.defaultTipText

    def _on_char(self, wrapped_evt):
        """Keyboard input to the patchers list box"""
        if wrapped_evt.key_code == 1 and wrapped_evt.is_cmd_down: # Ctrl+'A'
            patcher = self.currentPatcher
            if patcher is not None:
                patcher.mass_select(select=not wrapped_evt.is_shift_down)
                return
