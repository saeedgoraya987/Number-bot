#!/bin/bash
npm install
PORT=3000 node baileys_server.js &
sleep 15
python bot.py