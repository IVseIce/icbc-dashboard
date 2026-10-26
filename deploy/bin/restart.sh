#!/bin/bash
set -u
here=$(cd "$(dirname "$0")" && pwd)
bash "$here/stop.sh"
sleep 1
bash "$here/start.sh"
