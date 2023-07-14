from network import AgeNet
import numpy as np
import os
import argparse
from torch_geometric.data import Data
import torch
import torch.nn.functional as F
from utils.dataset import gnnAgeDataSet
from torch_geometric.loader import DataLoader
import collections
from sklearn.metrics import confusion_matrix
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib
"""

This file is in place to run inference on the trained model

"""

font = {'family' : 'Times New Roman',
        'weight' : 'bold',
        'size'   : 32}
plt.rcParams['figure.dpi'] =300
plt.rcParams['figure.figsize'] = (23,16)
matplotlib.rc('font', **font)

def get_args():
    """
    Grabs all hyperparameter values from the config file specified when running ./inf.sh
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('-batch_size', type=int, default=1, help='batch_size')
    parser.add_argument('-seed', type=int, default=24, help='seed')
    parser.add_argument('-num_epochs', type=int, default=100, help='num_epochs')
    parser.add_argument('-n_classes', type=int, default=100, help='n_classes')
    parser.add_argument('-early_stop', type=int, default=5, help='early_stop')
    parser.add_argument('-k_p', type=float, default=0.5, help='k_p')
    parser.add_argument('-num_features', type=int, default=100, help='num_features')
    parser.add_argument('-lat_dim', type=int, default=5, help='lat_dim')
    parser.add_argument('-Re_size', type=int, default=5, help='Re_size')
    parser.add_argument('-baffle_size', type=int, default=5, help='baffle_size')
    parser.add_argument('-dbl_size', type=int, default=5, help='dbl_size')
    parser.add_argument('-lr', type=float, default=0.01, help='lr')
    parser.add_argument('-max_v', type=float, default=1.00, help='max_v')
    parser.add_argument('-max_L', type=float, default=0.01, help='max_L')
    parser.add_argument('-data_path', type=str, default='../data/', help='data_path')
    parser.add_argument('-device', type=str, default='cpu', help='device')
    parser.add_argument('-batch_norm', type=bool, default=False, help='batch_norm')
    parser.add_argument('-drop', type=float, nargs='+',default=[0.7], help='drop')
    parser.add_argument('-up_drop', type=float, nargs='+',default=[0.7], help='up_drop')
    parser.add_argument('-up_conv_dims', type=int, nargs='+',default=[200, 100, 50, 10], help='up_conv_dims')
    parser.add_argument('-down_conv_dims', type=int, nargs='+',default=[10, 50, 100, 200], help='down_conv_dims')
    parser.add_argument('-test', type=str, nargs='+',default='', help='test' )

    args, _ = parser.parse_known_args()

    return args


def find_max_iter(dir):
    """ Basic function to find the max iteration (the converged solution) in an OpenFOAM case"""
    numbers = []

    for d in os.scandir(f'testRuns/{dir}/'):
        if d.is_dir():
            try:
                numbers.append(int(d.name))
            except:
                continue

    return f'{max(numbers)}/'

def pred_to_contour(pred, data, max_iter):
    """ This function serves to generate the contour visualization for the ground truth and prediction"""
    labels_mat = []
    value_dict = collections.defaultdict(int)
    # norm_vals = np.asarray([0, 0.5, 1, 1.5, 2, 3, 5, 7, 9, 11]) # value mapping for prediction -> contour
    norm_vals = np.asarray([0,2,5,10,15,20,25,30,40,50])
    cats = 22.5*norm_vals

    for value in pred:
        labels_mat.append(cats[value.item()])
    """ == Lots of code to take the actual age file output from openfoam and create a clone with the GT and prediction values =="""
    with open(f'testRuns/{data}/{max_iter}age') as f:
        lines = f.readlines()
    f.close()

    begin = lines[0:21]
    begin_data = lines[21:23]
    num_of_cells = int(begin_data[0])
    age_data = np.asarray(lines[23:23+num_of_cells], dtype=float)

    end = lines[(23+num_of_cells):]
    
    full_file = []
    full_file_2 = []
    full_file.extend(begin)
    full_file_2.extend(begin)
    full_file.extend(begin_data)
    full_file_2.extend(begin_data)

    feature_values = np.empty_like(age_data)

    for i in labels_mat:
        full_file.append(str(i) + '\n')
    for i, val in enumerate(age_data):
        norm = val / 22.5
        categorized = False
        for j, cat in enumerate(norm_vals):
            if norm > cat:
                feature_values[i] = cats[j]
                categorized = True
        if not categorized:
            feature_values[i] = cats[-1]
        full_file_2.append(f'{feature_values[i]} \n')

                
    for val in end:
        """ Random hack to allow for the boundary values to not be the original values from the age file """
        try:
            if val.split()[1] == 'nonuniform':
                num_nodes = int(val.split()[3].split('(')[0])
                starting = f'{num_nodes}(0.0 '
                for i in range(num_nodes-2):
                    starting += '1.0 '
                starting += f'0.0);'
                new_val = f'{val.split()[0]}    {val.split()[1]} {val.split()[2]} {starting}'
                full_file.append(new_val)
                full_file_2.append(new_val)
            elif val.split()[1] == 'uniform':
                full_file.append(f'{val.split()[0]}    uniform 0;')
                full_file_2.append(f'{val.split()[0]}    uniform 0;')
            else:
                full_file.append(val)
                full_file_2.append(val)
        except:
            full_file.append(val)
            full_file_2.append(val)

    """ ==========================="""

    """ Write the output to the converged folder for simplicity and to be
        read in the foamToVTK command for visualization
    """
    with open(f'testRuns/{data}/{max_iter}age_norm_pred','w') as g:

        for i in full_file:
            g.write(i)
    g.close()

    with open(f'testRuns/{data}/{max_iter}age_norm_gt','w') as g:

        for i in full_file_2:
            g.write(i)
    g.close()

    return 0

def indcs_to_contour(indcs, max_iter, data):
    """ This function maps the indices selected in top k pooling and writes them to a contour for visualization """
    with open(f'testRuns/{data}/{max_iter}age') as f:
        lines = f.readlines()
    f.close()
    """ == Remapping for the original index in the whole mesh == """
    for i, index in enumerate(indcs):
        if i == 0:
            continue
        else:
            indcs[i] = indcs[i-1][index]
    """ ================================ """

    """ The rest of this matches with the logic in the write_prediction_to_contour function """
    full_file = []

    begin = lines[0:21]
    begin_data = lines[21:23]
    num_of_cells = int(begin_data[0])

    end = lines[(23+num_of_cells):]
    idex = 0
    full_file.extend(begin)
    full_file.extend(begin_data)

    for index_tensor in indcs:
        idex+=1
        full_file_write = []
        index_tensor.to('cpu')
        lines_init = torch.zeros(size=(num_of_cells,))
        lines_init[index_tensor] = idex
        full_file_write.extend(full_file)
        for value in lines_init:
            full_file_write.append(f'{value} \n')
        
        full_file_write.extend(end)

        with open(f'testRuns/{data}/{max_iter}topk_select_{idex}','w') as g:

            for i in full_file_write:
                g.write(i)
        g.close()

    return 0
@torch.no_grad()
def run_test(model, data, device):

    e = torch.load(f'testRuns/{data}/e_{data}.pt')
    x = torch.load(f'testRuns/{data}/f_{data}.pt')
    y = torch.load(f'testRuns/{data}/l10_{data}.pt')
    print(f'Case is {data}')
    #print(data[2])

    datapt = gnnAgeDataSet(feats_paths=[f'testRuns/{data}/f_{data}.pt'], edge_paths=[f'testRuns/{data}/e_{data}.pt'], label_paths=[f'testRuns/{data}/l10_{data}.pt'], test=True)
    loader = DataLoader(datapt, batch_size=1)

    for data_test in loader:
        data_test.to(device)
        out, indcs = model(data_test, test=True)
        loss = F.nll_loss(out, data_test.y)
        _, preds = torch.max(out, 1)
        cf_matrix = confusion_matrix(data_test.y.cpu(), preds.cpu())
        plt.figure()
        sns.heatmap(cf_matrix, annot=True)
        plt.savefig(f'/home/john/repos/gnnUnetAge/confMats/big_{data}.png')
        plt.close()
        acc = torch.mean((preds == data_test.y).float())
    return acc.item(), loss.item(), preds, indcs

if __name__ == "__main__":
    device = "cuda"
    args = get_args()
    model = AgeNet(args,conv_act=F.relu, pool_act=F.relu, device=device)
    model.load_state_dict(torch.load('models/sc_final_model_lr_0.001_depth_3_k_0.7'))
    model.to(device)
    #model.eval()
    test_files = []
    for d in os.scandir('testRuns/'):

        if d.is_dir():
            test_files.append(d.name)
    for test in test_files:
        test_acc, test_loss, test_preds, indcs = run_test(model, data=test, device=device)
        max_iter = find_max_iter(test)
        pred_to_contour(data=test, pred=test_preds, max_iter=max_iter)
        indcs_to_contour(indcs=indcs, max_iter=max_iter, data=test)
        print(f'Loss is {test_loss}')
        print(f'Acc is {test_acc}')
