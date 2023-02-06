import torch
import torch.nn as nn
from torch_geometric.nn import SAGEConv, BatchNorm, GCNConv
from torch_geometric.utils import to_dense_adj, dense_to_sparse, add_self_loops, remove_isolated_nodes
import numpy as np
import math


class bigConv(nn.Module):

    def __init__(self, in_dim, out_dim, act, p, batchNorm):

        super(bigConv, self).__init__()
        self.conv = SAGEConv(in_dim, out_dim)
        self.act = act
        self.drop = nn.Dropout(p=p) if p > 0.0 else nn.Identity()
        self.batchNorm = BatchNorm(in_dim) if batchNorm else nn.Identity()

    def forward(self, x, edge_index):
        edge_index = add_self_loops(edge_index)[0]

        l1 = self.batchNorm(x)
        l1 = self.conv(x, edge_index)
        l1 = self.drop(l1)
        l1 = self.act(l1)

        return l1


class graphConvPool(nn.Module):

    def __init__(self, k, in_dim, act):
        super(graphConvPool, self).__init__()
        self.k = k
        self.scoregen = GCNConv(in_dim, 1)
        self.act = act

    def remove_obstacle(self,max, shape, indices):
        if max >= shape:
            idx = torch.argmax(indices[0]).item()
            indices_2 = torch.cat([indices[0][0:idx], indices[0][idx+1:]])
            indices_2 = torch.reshape(indices_2, (1, indices_2.shape[0]))
            new_max = torch.max(indices_2[0]).item()
            return self.remove_obstacle(new_max, shape, indices_2)
            
        else:
            return max, shape, indices

    def top_k_pool(self, g, e1, scores):
        num_nodes = scores.shape[0]
        scores = scores.T
        pooled, indices = torch.topk(scores, max(2, math.floor(self.k*num_nodes)))
        new_g = g[indices,:]
        new_g = new_g[0]
        e1 = to_dense_adj(e1)
        m, s, indices = self.remove_obstacle(torch.max(indices[0]).item(), e1.shape[1], indices)
        new_g = g[indices,:]
        new_g = new_g[0]
        e1 = e1[0][indices, :]
        e1 = e1[0].T
        e1 = e1[indices, :]
        e1 = e1[0].T
        e1 = e1.nonzero().t().contiguous()

        return new_g, e1, indices
        
    def forward(self, x, edge_index):
        p1 = self.scoregen(x, edge_index)
        return self.top_k_pool(x, edge_index, p1)

class graphConvUnpool(nn.Module):

    def __init__(self,  act):
        super(graphConvUnpool, self).__init__()
        self.act = act
        #self.unpoolconv = GCNConv(dim1, dim2)

    def forward(self, x_skip, e_skip, indices, x):

        unpooled_x = torch.zeros(size=x_skip.shape)
        #indices = indices.squeeze()
        unpooled_x[indices] = x
        #unpooled_x = self.unpoolconv(unpooled_x, e_skip)
        return self.act(unpooled_x), e_skip


class maxDeltaAgeLoss:

    def __init__(self, args, e, pred):
        self.max_v = args.max_v
        self.max_L = args.max_L
        self.e = e
        self.pred = pred

    def delta_mat_gen(self):
        # adj_mat = to_dense_adj(self.e)
        new_mat = adj_mat*self.pred[None, :]
        subbed = torch.sub(new_mat, self.pred)
        delta_mat = subbed*adj_mat
        return delta_mat
    
    def loss(self):
        delta_mat = self.delta_mat_gen()
        error_mat = delta_mat - (self.max_L / self.max_v)
        error_mat = torch.nn.functional.relu(error_mat, inplace=True)
        return torch.sum(error_mat) / len(error_mat[0]) 


