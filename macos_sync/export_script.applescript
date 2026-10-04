tell application "Calendar"
    set todayStart to current date
    set time of todayStart to 0
    set todayStart to todayStart - (2 * days)
    set todayEnd to todayStart + (60 * days)
    
    set outText to ""
    
    repeat with c in calendars
        set cName to name of c
        try
            set evs to (every event of c whose start date >= todayStart and start date <= todayEnd)
            repeat with ev in evs
                set sDate to (start date of ev as «class isot» as string)
                set eDate to (end date of ev as «class isot» as string)
                set sSumm to (summary of ev)
                set isAllDay to (allday event of ev)
                set evId to (uid of ev)
                set sDesc to ""
                try
                    set sDesc to (description of ev)
                    if sDesc is missing value then set sDesc to ""
                end try
                set sLoc to ""
                try
                    set sLoc to (location of ev)
                    if sLoc is missing value then set sLoc to ""
                end try
                
                -- replace linefeeds to keep on single line
                set AppleScript's text item delimiters to linefeed
                set tItems to text items of sDesc
                set AppleScript's text item delimiters to " "
                set sDesc to tItems as string
                
                set tItems to text items of sLoc
                set AppleScript's text item delimiters to " "
                set sLoc to tItems as string

                set outText to outText & evId & "|||" & sDate & "|||" & eDate & "|||" & (isAllDay as string) & "|||" & cName & "|||" & sSumm & "|||" & sLoc & "|||" & sDesc & linefeed
            end repeat
        end try
    end repeat
    
    return outText
end tell
