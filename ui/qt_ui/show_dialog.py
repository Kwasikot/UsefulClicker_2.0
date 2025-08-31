"""
Simple standalone script that shows an example Qt dialog.

Usage:
  python show_dialog.py

The dialog contains a label, a text input, a combo box and OK/Cancel buttons.
On OK the script prints the collected values and exits.
"""
import sys
import argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--auto-close', type=float, default=0.0,
                    help='If >0, automatically accept the dialog after given seconds (useful for demos)')
    args = ap.parse_args()

    try:
        from PyQt5 import QtWidgets, QtCore
    except Exception as e:
        print('PyQt5 is required to run this dialog. Import failed:', e)
        return 2

    class ExampleDialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle('Example Dialog — UsefulClicker')
            self.setMinimumSize(400, 160)
            layout = QtWidgets.QVBoxLayout(self)

            lbl = QtWidgets.QLabel('This is a test dialog for the UsefulClicker Qt frontend.')
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

            form = QtWidgets.QFormLayout()
            self.name_edit = QtWidgets.QLineEdit(self)
            self.name_edit.setPlaceholderText('Enter a name (example)')
            form.addRow('Name:', self.name_edit)

            self.mode_box = QtWidgets.QComboBox(self)
            self.mode_box.addItems(['Play', 'Pause', 'Restart', 'Next'])
            form.addRow('Action:', self.mode_box)

            layout.addLayout(form)

            self.info_label = QtWidgets.QLabel('Choose an action and press OK to print the result to stdout.')
            self.info_label.setWordWrap(True)
            layout.addWidget(self.info_label)

            btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            btns.accepted.connect(self.accept)
            btns.rejected.connect(self.reject)
            layout.addWidget(btns)

    app = QtWidgets.QApplication(sys.argv)
    dlg = ExampleDialog()

    if args.auto_close and args.auto_close > 0.0:
        QtCore.QTimer.singleShot(int(args.auto_close * 1000), dlg.accept)

    res = dlg.exec_()
    if res == QtWidgets.QDialog.Accepted:
        name = dlg.name_edit.text().strip()
        action = dlg.mode_box.currentText()
        print('DIALOG_RESULT: accepted')
        print('name=%r' % name)
        print('action=%r' % action)
        return 0
    else:
        print('DIALOG_RESULT: cancelled')
        return 1

if __name__ == '__main__':
    sys.exit(main())
