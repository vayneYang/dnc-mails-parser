#!/bin/bash
for i in `seq 1 59258`
do
wget https://wikileaks.org/dnc-emails//get/$i > $i.eml
done
