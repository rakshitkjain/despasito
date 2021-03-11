#!/bin/bash

awk '{print $1 , $2 , $3*4.587155963 ",", $4*4.587155963 }' decylbenzene_input.txt > decylbenzene_input.csv
