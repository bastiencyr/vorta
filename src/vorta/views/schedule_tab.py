from PyQt5 import uic, QtCore
from PyQt5.QtWidgets import QListWidgetItem, QApplication, QTableView, QHeaderView, QTableWidgetItem
from vorta.utils import get_asset, get_sorted_wifis
from vorta.models import EventLogModel, WifiSettingModel, BackupProfileMixin, BackupProfileModel
from vorta.views.utils import get_colored_icon

uifile = get_asset('UI/scheduletab.ui')
ScheduleUI, ScheduleBase = uic.loadUiType(uifile)


class LogTableColumn:
    Time = 0
    Category = 1
    Subcommand = 2
    Repository = 3
    ReturnCode = 4


class ScheduleTab(ScheduleBase, ScheduleUI, BackupProfileMixin):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(parent)
        self.app = QApplication.instance()
        self.toolBox.setCurrentIndex(0)

        self.schedulerRadioMapping = {
            'off': self.scheduleOffRadio,
            'interval': self.scheduleIntervalRadio,
            'fixed': self.scheduleFixedRadio
        }

        # Set up log table
        self.logTableWidget.setAlternatingRowColors(True)
        header = self.logTableWidget.horizontalHeader()
        header.setVisible(True)
        [header.setSectionResizeMode(i, QHeaderView.ResizeToContents) for i in range(5)]
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.logTableWidget.setSelectionBehavior(QTableView.SelectRows)
        self.logTableWidget.setEditTriggers(QTableView.NoEditTriggers)

        # Populate with data
        self.populate_from_profile()
        self.set_icons()

        # Connect events

        # prune old
        self.pruneCheckBox.stateChanged.connect(self.update_prune)

        # validate repository
        self.validationSpinBox.valueChanged.connect(self.update_validation_value)
        self.validationCheckBox.stateChanged.connect(self.update_validation_check)

        # backup manually (off)
        self.scheduleOffRadio.toggled.connect(self.update_manually)

        # backup every (interval)
        self.scheduleIntervalRadio.toggled.connect(self.update_interval_button)
        self.scheduleIntervalHours.valueChanged.connect(self.update_interval_hours)
        self.scheduleIntervalMinutes.valueChanged.connect(self.update_interval_minutes)

        # backup daily (fixed)
        self.scheduleFixedRadio.toggled.connect(self.update_fixed_button)
        self.scheduleFixedTime.timeChanged.connect(self.update_fixed_time)

        self.app.backup_finished_event.connect(self.populate_logs)
        self.dontRunOnMeteredNetworksCheckBox.stateChanged.connect(
            lambda new_val, attr='dont_run_on_metered_networks': self.save_profile_attr(attr, new_val))
        self.postBackupCmdLineEdit.textEdited.connect(
            lambda new_val, attr='post_backup_cmd': self.save_profile_attr(attr, new_val))
        self.preBackupCmdLineEdit.textEdited.connect(
            lambda new_val, attr='pre_backup_cmd': self.save_profile_attr(attr, new_val))
        self.createCmdLineEdit.textEdited.connect(
            lambda new_val, attr='create_backup_cmd': self.save_repo_attr(attr, new_val))

    def set_icons(self):
        self.toolBox.setItemIcon(0, get_colored_icon('clock-o'))
        self.toolBox.setItemIcon(1, get_colored_icon('wifi'))
        self.toolBox.setItemIcon(2, get_colored_icon('tasks'))
        self.toolBox.setItemIcon(3, get_colored_icon('terminal'))

    def populate_from_profile(self):
        """Populate current view with data from selected profile."""
        profile = self.profile()
        self.schedulerRadioMapping[profile.schedule_mode].setChecked(True)

        self.scheduleIntervalHours.setValue(profile.schedule_interval_hours)
        self.scheduleIntervalMinutes.setValue(profile.schedule_interval_minutes)
        self.scheduleFixedTime.setTime(
            QtCore.QTime(profile.schedule_fixed_hour, profile.schedule_fixed_minute))

        # Set checking options
        self.validationCheckBox.setCheckState(profile.validation_on)
        self.validationSpinBox.setValue(profile.validation_weeks)

        self.pruneCheckBox.setCheckState(profile.prune_on)
        self.validationCheckBox.setTristate(False)
        self.pruneCheckBox.setTristate(False)

        self.dontRunOnMeteredNetworksCheckBox.setChecked(profile.dont_run_on_metered_networks)

        self.preBackupCmdLineEdit.setText(profile.pre_backup_cmd)
        self.postBackupCmdLineEdit.setText(profile.post_backup_cmd)
        if profile.repo:
            self.createCmdLineEdit.setText(profile.repo.create_backup_cmd)
            self.createCmdLineEdit.setEnabled(True)
        else:
            self.createCmdLineEdit.setEnabled(False)

        self._draw_next_scheduled_backup()
        self.populate_wifi()
        self.populate_logs()

    def populate_wifi(self):
        self.wifiListWidget.clear()
        for wifi in get_sorted_wifis(self.profile()):
            item = QListWidgetItem()
            item.setText(wifi.ssid)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            if wifi.allowed:
                item.setCheckState(QtCore.Qt.Checked)
            else:
                item.setCheckState(QtCore.Qt.Unchecked)
            self.wifiListWidget.addItem(item)
        self.wifiListWidget.itemChanged.connect(self.save_wifi_item)

    def save_wifi_item(self, item):
        db_item = WifiSettingModel.get(ssid=item.text(), profile=self.profile().id)
        db_item.allowed = item.checkState() == 2
        db_item.save()

    def save_profile_attr(self, attr, new_value):
        profile = self.profile()
        setattr(profile, attr, new_value)
        profile.save()

    def save_repo_attr(self, attr, new_value):
        repo = self.profile().repo
        setattr(repo, attr, new_value)
        repo.save()

    def populate_logs(self):
        event_logs = [s for s in EventLogModel.select().order_by(EventLogModel.start_time.desc())]

        sorting = self.logTableWidget.isSortingEnabled()
        self.logTableWidget.setSortingEnabled(False)  # disable sorting while modifying the table.
        self.logTableWidget.setRowCount(len(event_logs))  # go ahead and set table length and then update the rows
        for row, log_line in enumerate(event_logs):
            formatted_time = log_line.start_time.strftime('%Y-%m-%d %H:%M')
            self.logTableWidget.setItem(row, LogTableColumn.Time, QTableWidgetItem(formatted_time))
            self.logTableWidget.setItem(row, LogTableColumn.Category, QTableWidgetItem(log_line.category))
            self.logTableWidget.setItem(row, LogTableColumn.Subcommand, QTableWidgetItem(log_line.subcommand))
            self.logTableWidget.setItem(row, LogTableColumn.Repository, QTableWidgetItem(log_line.repo_url))
            self.logTableWidget.setItem(row, LogTableColumn.ReturnCode, QTableWidgetItem(str(log_line.returncode)))
        self.logTableWidget.setSortingEnabled(sorting)  # restore sorting now that modifications are done

    def _draw_next_scheduled_backup(self):
        self.nextBackupDateTimeLabel.setText(self.app.scheduler.next_job_for_profile(self.profile().id))
        self.nextBackupDateTimeLabel.repaint()

    def update_prune(self):
        # update prune option.
        profile = BackupProfileModel.get(id=self.window().current_profile.id)
        profile.prune_on = self.pruneCheckBox.isChecked()
        profile.save()

    def update_validation_check(self):
        # update check value of "validate repository data" option
        profile = BackupProfileModel.get(id=self.window().current_profile.id)
        profile.validation_on = self.validationCheckBox.isChecked()
        profile.save()

    def update_validation_value(self):
        # update value of "validate repository data" option
        profile = BackupProfileModel.get(id=self.window().current_profile.id)
        profile.validation_weeks = self.validationSpinBox.value()
        profile.save()

    def update_manually(self):
        # update manually option
        profile = BackupProfileModel.get(id=self.window().current_profile.id)
        if self.scheduleOffRadio.isChecked():
            profile.schedule_mode = 'off'
            profile.save()
            self.app.scheduler.reload()
            self._draw_next_scheduled_backup()

    def update_interval_button(self):
        # update "backup every" option
        profile = BackupProfileModel.get(id=self.window().current_profile.id)
        label = 'interval'
        profile.schedule_mode = label
        profile.save()
        self.app.scheduler.reload()
        self._draw_next_scheduled_backup()

    def update_interval_hours(self):
        # update "backup every" option
        profile = BackupProfileModel.get(id=self.window().current_profile.id)
        profile.schedule_interval_hours = self.scheduleIntervalHours.value()
        profile.save()
        self.app.scheduler.reload()
        self._draw_next_scheduled_backup()

    def update_interval_minutes(self):
        # update "backup every" option
        profile = BackupProfileModel.get(id=self.window().current_profile.id)
        profile.schedule_interval_minutes = self.scheduleIntervalMinutes.value()
        profile.save()
        self.app.scheduler.reload()
        self._draw_next_scheduled_backup()

    def update_fixed_button(self):
        # update daily option
        profile = BackupProfileModel.get(id=self.window().current_profile.id)
        profile.schedule_mode = 'fixed'
        profile.save()
        self.app.scheduler.reload()
        self._draw_next_scheduled_backup()

    def update_fixed_time(self):
        # update daily option value
        profile = BackupProfileModel.get(id=self.window().current_profile.id)
        qtime = self.scheduleFixedTime.time()
        profile.schedule_fixed_hour, profile.schedule_fixed_minute = qtime.hour(), qtime.minute()
        profile.save()
        self.app.scheduler.reload()
        self._draw_next_scheduled_backup()
