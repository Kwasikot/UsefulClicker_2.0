@echo off
python -m input.pre_switch_layout
rem python main.py examples/anymusic_youtube.xml --debug
rem python main.py examples/curiosity_drive_test_broad_topics.xml --debug
python main.py examples/calm_content.xml --debug
set VOICE_DEVICE = 1
set VOICE_WAIT_SECONDS = 60
set DEBUG_DUMP_VOICE = 1
rem python usefulclicker_runner.py
