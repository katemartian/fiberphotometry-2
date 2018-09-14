from tkinter import Tk
from tkinter.filedialog import askopenfilename
import os
import peakutils
from collections import Counter
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter, freqz
import pandas as pd

def openfiledialogue(whichending):
    root = Tk()
    ftypes = [('LVM file',f"*{whichending}"),("All Files","*.*")]
    ttl = "Select file"

    if os.name == 'nt':
        dir1 = 'D:\\data\\2015'
        #dir1 = 'C:\\'   # Windows
    else:
        dir1 = '/Volumes/Zhivaz/'

    root.focus_force()
    # root.withdraw()
    file_path = askopenfilename(filetypes = ftypes, initialdir = dir1, title = ttl)
    root.deiconify(), root.update(), root.destroy()
    return file_path

def detect_stim_paradigm(stimchannel, fs):
    '''
    only works for evenly spaced block paradigms with constant ISI
    '''
    peakindexes = peakutils.indexes(stimchannel, thres=0.6, min_dist=0.01*fs)
    peakindexes_sec=peakindexes/fs
    delays = np.around(np.diff(peakindexes_sec),decimals=2)
    x = Counter(delays)   #counts elements in the input, and then shows which is most frequent, how often it appears etc...
    x1 = x.most_common(1)
    n_pulses = x1[0][1]
    x2 = x.most_common()[:-2:-1]  #find the longest delay (i.e. the least common value)
    n_blocks = x2[0][1] + 1
    stim_freq = np.round(1 / x1[0][0])  #remove round() for stim <1Hz
    pulses_block = n_pulses / n_blocks + 1
    block_duration = np.round(pulses_block / stim_freq)
    off_period = x2[0][0] - x1[0][0]
    print('stim freq: ' + str(stim_freq) + 'Hz')
    print('ON period: ' + str(block_duration) + 's')
    print('OFF period: ' + str(off_period) + 's')
    period = (block_duration + off_period) * 2
    print('Signals slower than ' + str(period) + 's will be removed (later)')
    return n_pulses, n_blocks, stim_freq, pulses_block, block_duration, off_period, peakindexes_sec, peakindexes


def FFT_calculate_plot(calcium, fs, plotsize):
    f1, Pxx_den1 = signal.welch(calcium['channel1','raw'], fs, nperseg=65536)

    fig = plt.figure(figsize=plotsize)
    ax = plt.axes()
    ax.semilogy(f1, Pxx_den1, label='channel 1')
    ax.set_xlabel('frequency [Hz]')
    ax.set_ylabel('PSD [V**2/Hz]')
    ax.set_title('Frequency spectra of raw signals')

    f2, Pxx_den2 = signal.welch(calcium['channel2','raw'],fs,nperseg=65536)
    ax.semilogy(f2, Pxx_den2, label='channel 2')
    ax.set_xlim(500, 0.2*fs)
    ax.legend()

    # Detect modulation frequencies automatically by getting highest peak
    if 'mod_ch1' not in locals():
        mod_ch1 = np.around(f1[np.argmax(Pxx_den1)],decimals=0)
    if 'mod_ch2' not in locals():
        mod_ch2 = np.around(f2[np.argmax(Pxx_den2)],decimals=0)
    return mod_ch1, mod_ch2


def addReferences(calcium, mod_ch1, mod_ch2):
    """
    Adds sine and cosine reference waves to dataframe with given frequencies 
    """
    # create reference sin + cos wave forms
    calcium['channel1','sin_ref'] = np.sin(2*np.pi*mod_ch1*calcium.index.values)
    calcium['channel1','cos_ref'] = np.cos(2*np.pi*mod_ch1*calcium.index.values)

    calcium['channel2','sin_ref'] = np.sin(2*np.pi*mod_ch2*calcium.index.values)
    calcium['channel2','cos_ref'] = np.cos(2*np.pi*mod_ch2*calcium.index.values)

    # multiply them with raw signals
    calcium['channel1', 'demod_sin'] = calcium['channel1', 'raw']*calcium['channel1', 'sin_ref']
    calcium['channel1', 'demod_cos'] = calcium['channel1', 'raw']*calcium['channel1', 'cos_ref']

    calcium['channel2', 'demod_sin'] = calcium['channel2', 'raw']*calcium['channel2', 'sin_ref']
    calcium['channel2', 'demod_cos'] = calcium['channel2', 'raw']*calcium['channel2', 'cos_ref']
    return calcium


def butter_lowpass(cutoff, fs, order):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return b, a


def butter_lowpass_filter(data, cutoff, fs, order):
    b, a = butter_lowpass(cutoff, fs, order)
    y = lfilter(b, a, data)
    return y

def calc_cutoff_freqs(mod_ch1, mod_ch2):
    cutoff=np.empty([4])
    # initial filter to the sin/cos signal separately
    cutoff[0] = mod_ch1+500
    cutoff[1] = mod_ch1-100

    # final filtering for the combined signal
    cutoff[2] = mod_ch2+100
    cutoff[3] = mod_ch2-500
    return cutoff

def demodulate(calcium, mod_ch1, mod_ch2, fs, peakindexes_sec):
    """
    References and detailed description to be added
    """
    # Filter settings (adjust if laser frequencies change)
    order = 9
    cutoff = calc_cutoff_freqs(mod_ch1, mod_ch2)
    
    # apply initial low pass filter
    calcium['channel1', 'demod_sin_filtered'] = butter_lowpass_filter(calcium['channel1','demod_sin'], cutoff[0], fs, order)
    calcium['channel1', 'demod_cos_filtered'] = butter_lowpass_filter(calcium['channel1','demod_cos'], cutoff[0], fs, order)

    calcium['channel2', 'demod_sin_filtered'] = butter_lowpass_filter(calcium['channel2','demod_sin'], cutoff[2], fs, order)
    calcium['channel2', 'demod_cos_filtered'] = butter_lowpass_filter(calcium['channel2','demod_cos'], cutoff[2], fs, order)

    # Combine the sin+cos signals, and apply final low pass filter.
    calcium['channel1', 'demod_tot']=1/2*np.sqrt(np.square(calcium['channel1','demod_sin_filtered'])+np.square(calcium['channel1','demod_cos_filtered']))
    calcium['channel1', 'demod_tot'] = butter_lowpass_filter(calcium['channel1','demod_tot'], cutoff[1], fs, order)

    calcium['channel2', 'demod_tot']=1/2*np.sqrt(np.square(calcium['channel2','demod_sin_filtered'])+np.square(calcium['channel2','demod_cos_filtered']))
    calcium['channel2', 'demod_tot'] = butter_lowpass_filter(calcium['channel2','demod_tot'], cutoff[3], fs, order)

    # Cut off some artifact at beginning caused by the filter.
    calcium = calcium.sort_index()
    calcium = calcium.iloc[300:, :] 
    peakindexes_sec = peakindexes_sec - 300/fs
    return calcium, peakindexes_sec


def plot_filter_stuff(calcium, which_freq, fs, plotsize):
    order = 9 # careful its hardcoded
    # Plot a few filter frequency responses and power spectra (channel 1)
    b, a = butter_lowpass(which_freq, fs, order)
    w, h = freqz(b, a, worN=8000)
    plt.figure(figsize=plotsize)
    plt.subplot(2, 1, 1)
    plt.plot(0.5*fs*w/np.pi, np.abs(h), 'b')
    plt.plot(which_freq, 0.5*np.sqrt(2), 'ko')
    plt.axvline(which_freq, color='k')
    plt.xlim(0, 0.2*fs)
    plt.title("Lowpass Filter Frequency Response")
    plt.xlabel('Frequency [Hz]')
    plt.grid()


    plt.subplot(2, 1, 2)
    f, Pxx_den = signal.welch(calcium['channel1','demod_sin'],fs,nperseg=2**16)
    plt.semilogy(f, Pxx_den, label='channel 1 * sin')
    f, Pxx_den = signal.welch(calcium['channel1','demod_sin_filtered'],fs,nperseg=2**16)
    plt.semilogy(f, Pxx_den, label='channel 1 * sin filtered')
    f, Pxx_den = signal.welch(calcium['channel1','demod_tot'],fs,nperseg=2**16)
    plt.semilogy(f, Pxx_den, label='channel 1 combined (filtered)')
    #f, Pxx_den = signal.welch(calcium['channel1','demod_combineBeforeFilter_b'],fs,nperseg=2**16)
    #plt.semilogy(f, Pxx_den, label='channel 1 total (filter AFTER combining)')
    #plt.ylim([0.5e-3, 1])
    plt.xlabel('frequency [Hz]')
    plt.ylabel('PSD [V**2/Hz]')
    plt.xlim(500, 0.3*fs)
    plt.legend()
    plt.subplots_adjust(hspace=0.35)
    

def downsamplebin(channel, timeres, sampling):
    N_samples = int(timeres*sampling)
    lastpoint = int(np.arange(0,np.size(channel), N_samples)[-1])
    out = np.reshape(channel[0:lastpoint], (-1, N_samples))
#     out = np.mean(out, axis=1)
    out = np.median(out, axis=1)
    return out

def fixjumps(data, data_x, ch, fs, tres_new, xSTD=6, secstoconsider=0.5):
    delta = 0
    binsize=int(secstoconsider*fs)
    data_cor=np.zeros(data.shape)
    data_cor[:binsize]=data[:binsize]
    data2=np.diff(data)
    data2=data2/np.max(data2)
        
    for i in np.arange(binsize,len(data_x)-1):
        meanprior=np.mean(data2[i-binsize:i-1])
        difference=data2[i]-meanprior
        threshold=np.std(data2[i-binsize:i-1])*xSTD
        if np.abs(difference) > threshold:
            print('jump detected in ' + ch + ' at '+ str(i*tres_new) + 's' )
            delta += np.median(data[i:i+binsize])-np.median(data[i-binsize:i-1])
            data_cor[i]=data[i]-delta
            data_cor[i]=np.median(data_cor[i-3:i])
        else:
            data_cor[i]=data[i]-delta
    data_cor[-1]=data[-1]-delta
    return data_cor
