# -*- coding: utf-8 -*-

from tkinter import *

from tkinter.filedialog import askopenfilename, askdirectory
import tkinter.tix as tix

# logger -----------------------------------------------
import logging
FORMAT = '%(asctime)-15s - %(levelname)s - %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger('GUI_list_files')
logger.setLevel(logging.DEBUG)
# ------------------------------------------------------

root = Tk()
root.wm_title("Generate file list")

frameLabel = Frame(root, height=4)
frameLabel.pack()
label = Label(frameLabel, text='Give a name to your search')
label.pack(side=LEFT)
entry = Entry(frameLabel, bd= 5)
entry.pack(side=RIGHT)

frameDir = Frame(root)
frameDir.pack()
labelDir = Label(frameDir, text="Dir to analyze")
labelDir.pack(side=LEFT)
dirnameVar = StringVar()

entryDir = Label(frameDir, textvariable=dirnameVar, bd = 5)
entryDir.pack(side=RIGHT)

frameSelect = Frame(root)

def askdir():
    dirName = askdirectory(parent=root)
    print('selected is %s '% dirName)
    dirnameVar.set(dirName)
    entryDir.setvar(name='text', value=dirName)
    return dirName

button = Button(frameSelect, text="select folder", command=askdir)
button.pack()
frameSelect.pack()

def process():
    import time
    import list_files
    try :
        t1 = time.time()
        files = list_files.find_files(dirnameVar.get(), entry.get(), _simpleSearch=isSimpleSearch.get())
        list_files.write_cvs(files, 'result.csv' )
        print()
        resultVar.set('Done in %d ms' % ((time.time() - t1)*1000))
    except :
        logger.exception('An exception occured during request')
        resultVar.set('An error occured please see the comand line terminal' )
    pass

buttonProcess= Button(root, text="GO", command = process)
buttonProcess.pack()
resultVar = StringVar()
resultVar.set('waiting')
labelResult = Label(root, textvariable=resultVar)
labelResult.pack()

isSimpleSearch = IntVar()
isSimpleSearch.set(1)
#def toggleSimple () :
#    if isSimpleSearch.get() :
#        isSimpleSearch.set(0)
#    else :
#        isSimpleSearch.set(1)
checkSimpleSearch = Checkbutton(root, text='Simple search', variable=isSimpleSearch)
checkSimpleSearch.pack()

def bindProcess(event):
    process()

root.bind("<Return>", bindProcess)
root.mainloop()

