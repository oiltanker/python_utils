import sys, os
from typing import Any
import inspect
import re

_masks = {
    'import': [re.compile(r'^import (.+)$'), re.compile(r'^from .+ import (.+)$')],
    'function': [re.compile(r'^def (.+)\(.*\).*:.*$')],
    'class': [re.compile(r'^class (.+)(\(.+\))?:.*$')],
    'global': [re.compile(r'^([^:]+)(\s*:[^=]+)?=.+$')]
}
_importAsMask = re.compile(r'^.+ as (.+)$')
def getTopDefs(srcProvider: Any) -> dict[str, list[str]]:
    DEBUG_PRINT = False
    DEBUG_STRIPPED_PRINT = False

    src: str
    if isinstance(srcProvider, str): src = srcProvider
    else:
        try: src = inspect.getsource(srcProvider)
        except: raise ValueError(f'Unable to obtains source from "srcProvider"')

    strippedSrc: list[str] = []
    tlSrc: list[str] = []
    slBuf: str = None

    sPtr, sLen = 0, len(src)
    sBuf: str = ''
    pStack = []
    while sPtr < sLen:
        if src[sPtr] in '"\'':
            isFmtStr = False
            if src[sPtr - 1] == 'f':
                isFmtStr = True
                if len(pStack) == 0: sBuf = sBuf[:-1]

            def parseStrTerm(sPtr: int) -> tuple[int, str]:
                def skipFmt(sPtr: int) -> int:
                    lpCnt = 1
                    sPtr += 1
                    while sPtr < sLen and lpCnt > 0:
                        if src[sPtr] == '{': lpCnt += 1
                        elif src[sPtr] == '}': lpCnt -= 1
                        elif src[sPtr] in '"\'':
                            sPtr, term = parseStrTerm(sPtr)
                            sPtr -= 1
                        sPtr += 1
                    return sPtr

                def skipNxtQuote(sPtr: int, nsPtr, q: str) -> int:
                    while sPtr < sLen and src[nsPtr] != q:
                        if isFmtStr and src[nsPtr] == '{': nsPtr = skipFmt(nsPtr)
                        elif src[nsPtr] == '\\': nsPtr += 2
                        else: nsPtr += 1
                    if nsPtr >= sLen:
                        if DEBUG_PRINT: print(src[sPtr:sLen] , end='')
                        raise ValueError('Module has incorrect source? (probably faulty processing)')
                    return nsPtr

                mqSlice, exMqSLice = src[sPtr:min(sLen, sPtr+3)], src[sPtr] * 3
                if mqSlice == exMqSLice: # triple quotes
                    endFound, nsPtr = False, sPtr+3
                    while not endFound:
                        nsPtr = skipNxtQuote(sPtr, nsPtr, src[sPtr])
                        if src[nsPtr:min(sLen, nsPtr+3)] == exMqSLice:
                            nsPtr += 3
                            endFound = True
                    if DEBUG_PRINT: print(src[sPtr:nsPtr] , end='')
                    return nsPtr, f'<{'f_' if isFmtStr else ''}t_{'d' if src[sPtr] == '"' else 's'}q_term>'
                else: # regular quotes
                    nsPtr = sPtr + 1
                    nsPtr = skipNxtQuote(sPtr, nsPtr, src[sPtr]) + 1 # last quote symbol reached, advance
                    if DEBUG_PRINT: print(src[sPtr:nsPtr] , end='')
                    return nsPtr, f'<{'f_' if isFmtStr else ''}{'d' if src[sPtr] == '"' else 's'}q_term>'
            sPtr, term = parseStrTerm(sPtr)
            if len(pStack) == 0: sBuf += term
        if sPtr >= sLen: continue
        
        if src[sPtr] == '#':
            nsPtr = sPtr + 1
            while nsPtr < sLen and src[nsPtr] != '\n': nsPtr += 1
            if DEBUG_PRINT: print(src[sPtr:nsPtr] , end='')
            sPtr = nsPtr # leave sPtr on \n for sBuf reset
            if len(pStack) == 0: sBuf += '<c_term>'
        if sPtr >= sLen: continue

        if src[sPtr] in '()[]{}': # parentheses
            if len(pStack) == 0 and src[sPtr] in ')]}':
                if DEBUG_PRINT: print(src[sPtr] , end='')
                raise ValueError('Module has incorrect source? (probably faulty processing)')
            else:
                if len(pStack) == 0: sBuf += src[sPtr] + '<p_term>'
                if src[sPtr] in '([{': pStack.append(src[sPtr])
                elif src[sPtr] == ')' and pStack[-1] == '(': pStack.pop()
                elif src[sPtr] == ']' and pStack[-1] == '[': pStack.pop()
                elif src[sPtr] == '}' and pStack[-1] == '{': pStack.pop()
                else:
                    if DEBUG_PRINT: print(src[sPtr] , end='')
                    raise ValueError('Module has incorrect source? (probably faulty processing)')

        if len(pStack) == 0: # not processing any literals
            if src[sPtr] != '\n':
                sBuf += src[sPtr]
            else:
                strippedSrc.append(sBuf)
                sBuf = ''
        if DEBUG_PRINT: print(src[sPtr] , end='')
        sPtr += 1
    del src
    if len(sBuf) != 0: strippedSrc.append(sBuf)
    if DEBUG_STRIPPED_PRINT:
        for sl in strippedSrc: print(sl)
    
    for sl in strippedSrc:
        if slBuf == None:
            if not sl.startswith(' '):
                sls = sl.rstrip()
                if len(sls) == 0: continue
                
                slss = sls.split(';')
                sls = slss[-1].lstrip(); slss = slss[:-1]
                for sle in slss: tlSrc.append(sle.strip())

                if sls.endswith('\\'): slBuf = sls[:-1].rstrip() + ' '
                else: tlSrc.append(sls)
        else:
            sls = sl.strip()

            slss = sls.split(';')
            sls = slss[0].rstrip(); slss = slss[1:]
            if len(slss) > 0:
                tlSrc.append(slBuf + sls)
                slBuf = None

                sls = slss[-1].lstrip(); slss = slss[:-1]
                for sle in slss: tlSrc.append(sle.strip())

                if sls.endswith('\\'): slBuf = sls[:-1].rstrip() + ' '
                else: tlSrc.append(sls)
            else:
                if sls.endswith('\\'): slBuf += sls[:-1].rstrip() + ' '
                else:
                    tlSrc.append(slBuf + sls)
                    slBuf = None
    del strippedSrc

    imports, functions, classes, globals, others = [], [], [], [], []
    def resAppend(k: str, val: str):
        val = val.strip()
        if   k == 'import':
            for imp in map(lambda v: v.strip(), val.split(',')):
                match = _importAsMask.fullmatch(imp)
                if match != None: imports.append(match.groups()[0].lstrip())
                else: imports.append(imp)
        elif k == 'function': functions.append(val)
        elif k == 'class': classes.append(val)
        elif k == 'global':
            for gdef in map(lambda v: v.strip(), val.split(',')): globals.append(gdef)
        else: others.append(val)
    for tld in tlSrc:
        found = False
        for k, masks in _masks.items():
            for mask in masks:
                match = mask.fullmatch(tld)
                if match != None:
                    resAppend(k, match.groups()[0])
                    found = True; break
            if found: break
        if not found: resAppend(None, tld)

    return {
        'import': imports,
        'function': functions,
        'class': classes,
        'global': globals,
        'other': others
    }

# print('\n -- this:')
# for k, v in getTopDefs(sys.modules[__name__]).items(): print(f'{k}: {v}')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f'Incorrect usage: {os.path.basename(__file__)} <path>', file=sys.stderr)
        sys.exit(1)
    try:
        with open(sys.argv[1], 'r') as f: src = f.read()
        defs = getTopDefs(src); del src
        print(f'\nTop level definitions for "{sys.argv[1]}":\n')
        mkLen = max(map(lambda k: len(k), defs.keys()))
        lSep = ' ' * (mkLen + 3)
        for k, vs in defs.items():
            line = f'{k + ' ' * (mkLen - len(k))} : '
            lLen, added = len(line), False
            for v in vs:
                vStr = f'\'{v}\', '
                vLen = len(vStr)
                if not added:
                    line += vStr
                    lLen += vLen
                    added = True
                else:
                    if lLen + vLen >= 80:
                        line += '\n' + lSep + vStr
                        lLen = len(lSep) + vLen
                    else:
                        line += vStr
                        lLen += vLen
            print(line[:-2] if added else line)
        print('\nAssumed __all__ = [')
        for v in filter(lambda d: not d.startswith('_'), defs['class']): print(f'    \'{v}\',')
        for v in filter(lambda d: not d.startswith('_'),defs['function']): print(f'    \'{v}\',')
        for v in filter(lambda d: not d.startswith('_'),defs['global']): print(f'    \'{v}\',')
        print(']')
        sys.exit(0)
    except Exception as ex:
        print(ex, file=sys.stderr)
        sys.exit(2)
