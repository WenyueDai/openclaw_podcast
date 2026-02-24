crontab -e #edit cron
crontab -l #list all cron
sudo journalctl -u cron --since "09:00" --until "09:10"

(.venv) eva@evadai:~/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio $ which node
/home/eva/.nvm/versions/node/v22.22.0/bin/node

(.venv) eva@evadai:~/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio $ env -i HOME=/home/eva PATH=/usr/bin:/bin bash -lc 'which node'

# check which feed (rss) are ok, which are not
python tools/check_feed.py


# check if run_daily.py is running
eva@evadai:~/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio $ pgrep -fl run_daily.py
12165 python
# check more detail about the job
eva@evadai:~/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio $ ps -fp 12165
UID          PID    PPID  C STIME TTY          TIME CMD
eva        12165   11703  0 Feb23 pts/1    00:00:01 python run_daily.py
# check elapsed time (etime-actual time period, stime-start time)
eva@evadai:~/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio $ ps -p 12165 -o pid,etime,stime,cmd
    PID     ELAPSED STIME CMD
  12165  1-04:04:28 Feb23 python run_daily.py

# check if it keep generating output
eva@evadai:~/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio $ ls -lt output 
total 8
drwxrwxr-x 2 eva eva 4096 Feb 24 22:13 feed_health
drwxrwxr-x 2 eva eva 4096 Feb 23 09:09 log
