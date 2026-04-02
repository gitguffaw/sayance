#!/bin/sh
# Set old timestamps on 2 files (5 days ago), leave new_web.conf recent.
# Run this in the fixture's working directory after copying.
touch -t 202501010000 conf/old_app.conf conf/old_db.conf
