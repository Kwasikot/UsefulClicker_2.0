@echo off
call .venv/Scripts/activate.bat
python -m input.pre_switch_layout
rem python main.py examples/anymusic_youtube.xml --debug
python main.py examples/curiosity_drive_test.xml --debug
