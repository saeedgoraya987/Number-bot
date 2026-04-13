#!/bin/bash
npm install
node baileys_server.js &
sleep 15
python bot.py