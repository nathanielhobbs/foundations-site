#!/bin/bash

filename="data/github_roster.csv"
section="$1" # The section number is the optional argument

echo "Students who are missing their GitHub account matching:"

awk -v FPAT='[^,]*|"[^"]*"' -v section="$section" '
    BEGIN {
        # Set a flag to determine if all sections should be printed
        if (section == "") {
            print_all = 1
        } else {
            print_all = 0
        }
    }
    
    # Skip the header row (NR > 1)
    # Check if the line matches either the specified section or if all sections should be printed
    NR > 1 && (print_all || $1 == section) && $NF == "" {
        # The full name is in the second field ($2)
        # We need to remove the surrounding double quotes
        name = $2
        gsub(/"/, "", name)

        print "Section " $1 ": " name
    }
' "$filename"
