medievo_GRAMMAR = r'''
start: line*

line: section_line NEWLINE?      -> section_line
    | subsection_line NEWLINE?   -> subsection_line
    | text_line NEWLINE?         -> text_line
    | NEWLINE                    -> blank_line

section_line: SECTION_LINE
subsection_line: SUBSECTION_LINE
text_line: TEXT_LINE

SECTION_LINE: /#+[ \t]*[^\s#>:|\r\n][^#>|\r\n]*/
SUBSECTION_LINE: />[ \t]*[^\r\n]+/
TEXT_LINE: /[ \t]*(?![#>:])(?=.*\S)[^\r\n]+/

%import common.NEWLINE
'''
