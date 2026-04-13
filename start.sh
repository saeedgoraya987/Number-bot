#!/bin/bash
npm install
node baileys_server.js &
sleep 5
python bot.py