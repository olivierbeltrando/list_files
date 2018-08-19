# -*- coding: utf-8 -*-

import os

from tkinter import *

from tkinter.filedialog import askopenfilename, askdirectory
import tkinter.tix as tix

# logger -----------------------------------------------
import logging
FORMAT = '%(asctime)-15s - %(levelname)s - %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# ------------------------------------------------------

root = Tk()
root.wm_title("Generate file list")

frameLabel = Frame(root, height=4)
frameLabel.pack()
label = Label(frameLabel, text='Give a name to your search')
label.pack(side=LEFT)
entry = Entry(frameLabel, bd=5)
entry.pack(side=RIGHT)

frameDir = Frame(root)
frameDir.pack()
labelDir = Label(frameDir, text="Dir to analyze")
labelDir.pack(side=LEFT)
dirnameVar = StringVar()

entryDir = Label(frameDir, textvariable=dirnameVar, bd=5)
entryDir.pack(side=RIGHT)

frameSelect = Frame(root)


def askdir():
    dirName = askdirectory(parent=root)
    print('selected is %s ' % dirName)
    dirnameVar.set(dirName)
    entryDir.setvar(name='text', value=dirName)
    return dirName


button = Button(frameSelect, text="select folder", command=askdir)
button.pack()
frameSelect.pack()


def process():
    import time
    import list_files
    try:
        t1 = time.time()
        files = list_files.find_files(
            dirnameVar.get(), entry.get(), _simpleSearch=isSimpleSearch.get())
        list_files.write_cvs(files, get_location())
        print()
        resultVar.set('Done in %d ms' % ((time.time() - t1)*1000))
    except:
        logger.exception('An exception occured during request')
        resultVar.set('An error occured please see the comand line terminal')


buttonProcess = Button(root, text="GO", command=process)
buttonProcess.pack()
resultVar = StringVar()
resultVar.set('waiting')
labelResult = Label(root, textvariable=resultVar)
labelResult.pack()

isSimpleSearch = IntVar()
isSimpleSearch.set(1)
# def toggleSimple () :
#    if isSimpleSearch.get() :
#        isSimpleSearch.set(0)
#    else :
#        isSimpleSearch.set(1)
checkSimpleSearch = Checkbutton(
    root, text='Simple search', variable=isSimpleSearch)
checkSimpleSearch.pack()

# -- TOGGLE BUTTON DEFAULT LOCATION ---
result_location = IntVar()
result_location.set(1)
Radiobutton(root, text="Store result in Home",
            variable=result_location, value=1).pack()
Radiobutton(root, text="Store result in search folder",
            variable=result_location, value=2).pack()


def get_location():
    if result_location.get() == 1:
        from pathlib import Path
        folder = Path.home()
    else:
        folder = dirnameVar.get()
    return os.path.join(folder, "result.csv")
# --


def bindProcess(event):
    process()


root.bind("<Return>", bindProcess)
try:
    root.mainloop()
except KeyboardInterrupt:
    logger.info("Keyboard interrupt detected. Clean exit")
