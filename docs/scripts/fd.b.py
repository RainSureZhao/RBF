''' 
This script demonstrates using the RBF-FD method to calculate static 
deformation of a two-dimensional elastic material subject to a uniform 
body force such as gravity. The elastic material has a fixed boundary 
condition on one side and the remaining sides have a free surface 
boundary condition.  This script also demonstrates using ghost nodes 
which, for all intents and purposes, are necessary when dealing with 
Neumann boundary conditions.
'''
import numpy as np
import scipy.sparse
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from rbf.nodes import min_energy_nodes
from rbf.fd import weight_matrix
import scipy.sparse.linalg as spla

def expand_rows(A,idx,n):
  A = scipy.sparse.coo_matrix(A)
  idx = np.asarray(idx,dtype=int)
  shape = (n,A.shape[1])
  out = scipy.sparse.csc_matrix((A.data,(idx[A.row],A.col)),shape=shape)
  return out


## User defined parameters
#####################################################################
# define the vertices of the problem domain. Note that the first 
# simplex will be fixed, and the others will be free
vert = np.array([[0.0,0.0],[0.0,1.0],[2.0,1.0],[2.0,0.0]])
smp = np.array([[0,1],[1,2],[2,3],[3,0]])
# number of nodes 
N = 200
# size of RBF-FD stencils
n = 20
# lame parameters
lamb = 1.0
mu = 1.0
# z component of body force
body_force = 1.0

order = 2

## Build and solve for displacements and strain
#####################################################################
# generate nodes. Read the documentation for *menodes* to tune it and 
# allow for variable node densities.
boundary_groups = {'fixed':[0],
                   'free':[1,2,3]}
nodes,indices,normals = min_energy_nodes(N,vert,smp,itr=401,
                          boundary_groups=boundary_groups,
                          boundary_groups_with_ghosts=['free'],
                          return_normals=True)
# redefine N based on how many nodes we actually have
N = nodes.shape[0]
free_idx = indices['free']
fixed_idx = indices['fixed']
interior_and_free_idx = np.hstack((indices['interior'],indices['free']))
interior_and_ghosts_idx = np.hstack((indices['interior'],indices['free_ghosts']))
interior_and_boundary_idx = np.hstack((indices['interior'],indices['free'],indices['fixed']))

## Enforce the PDE on interior nodes AND the free surface nodes 
# x component of force resulting from displacement in the x direction.
coeffs_xx = [lamb+2*mu,mu]
diffs_xx = [(2,0),(0,2)]
# x component of force resulting from displacement in the y direction.
coeffs_xy = [lamb,mu]
diffs_xy = [(1,1),(1,1)]
# y component of force resulting from displacement in the x direction.
coeffs_yx = [mu,lamb]
diffs_yx = [(1,1),(1,1)]
# y component of force resulting from displacement in the y direction.
coeffs_yy = [lamb+2*mu,mu]
diffs_yy =  [(0,2),(2,0)]
# make the differentiation matrices that enforce the PDE on the 
# interior nodes.
D_xx = weight_matrix(nodes[interior_and_free_idx],nodes,diffs_xx,coeffs=coeffs_xx,n=n,order=order)
D_xx = expand_rows(D_xx,interior_and_ghosts_idx,N)

D_xy = weight_matrix(nodes[interior_and_free_idx],nodes,diffs_xy,coeffs=coeffs_xy,n=n,order=order)
D_xy = expand_rows(D_xy,interior_and_ghosts_idx,N)

D_yx = weight_matrix(nodes[interior_and_free_idx],nodes,diffs_yx,coeffs=coeffs_yx,n=n,order=order)
D_yx = expand_rows(D_yx,interior_and_ghosts_idx,N)

D_yy = weight_matrix(nodes[interior_and_free_idx],nodes,diffs_yy,coeffs=coeffs_yy,n=n,order=order)
D_yy = expand_rows(D_yy,interior_and_ghosts_idx,N)

# stack them together
D_x = scipy.sparse.hstack((D_xx,D_xy))
D_y = scipy.sparse.hstack((D_yx,D_yy))
D = scipy.sparse.vstack((D_x,D_y))
## Enforce fixed boundary conditions
# Enforce that x and y are as specified with the fixed boundary 
# condition. These matrices turn out to be identity matrices, but I 
# include this computation for consistency with the rest of the code. 
# feel free to comment out the next couple lines and replace it with 
# an appropriately sized sparse identity matrix.
coeffs_xx = [1.0]
diffs_xx = [(0,0)]
coeffs_xy = [0.0]
diffs_xy = [(0,0)]
coeffs_yx = [0.0]
diffs_yx = [(0,0)]
coeffs_yy = [1.0]
diffs_yy = [(0,0)]

dD_fix_xx = weight_matrix(nodes[fixed_idx],nodes,diffs_xx,coeffs=coeffs_xx,n=n,order=order)
dD_fix_xx = expand_rows(dD_fix_xx,fixed_idx,N)

dD_fix_xy = weight_matrix(nodes[fixed_idx],nodes,diffs_xy,coeffs=coeffs_xy,n=n,order=order)
dD_fix_xy = expand_rows(dD_fix_xy,fixed_idx,N)

dD_fix_yx = weight_matrix(nodes[fixed_idx],nodes,diffs_yx,coeffs=coeffs_yx,n=n,order=order)
dD_fix_yx = expand_rows(dD_fix_yx,fixed_idx,N)

dD_fix_yy = weight_matrix(nodes[fixed_idx],nodes,diffs_yy,coeffs=coeffs_yy,n=n,order=order)
dD_fix_yy = expand_rows(dD_fix_yy,fixed_idx,N)

dD_fix_x = scipy.sparse.hstack((dD_fix_xx,dD_fix_xy))
dD_fix_y = scipy.sparse.hstack((dD_fix_yx,dD_fix_yy))
dD_fix = scipy.sparse.vstack((dD_fix_x,dD_fix_y))

## Enforce free surface boundary conditions
# x component of traction force resulting from x displacement 
coeffs_xx = [normals['free'][:,0]*(lamb+2*mu),normals['free'][:,1]*mu]
diffs_xx = [(1,0),(0,1)]
# x component of traction force resulting from y displacement
coeffs_xy = [normals['free'][:,0]*lamb,normals['free'][:,1]*mu]
diffs_xy = [(0,1),(1,0)]
# y component of traction force resulting from x displacement
coeffs_yx = [normals['free'][:,0]*mu,normals['free'][:,1]*lamb]
diffs_yx = [(0,1),(1,0)]
# y component of force resulting from displacement in the y direction
coeffs_yy = [normals['free'][:,1]*(lamb+2*mu),normals['free'][:,0]*mu]
diffs_yy =  [(0,1),(1,0)]
# make the differentiation matrices that enforce the free surface boundary 
# conditions.
dD_free_xx = weight_matrix(nodes[free_idx],nodes,diffs_xx,coeffs=coeffs_xx,n=n,order=order)
dD_free_xx = expand_rows(dD_free_xx,free_idx,N)

dD_free_xy = weight_matrix(nodes[free_idx],nodes,diffs_xy,coeffs=coeffs_xy,n=n,order=order)
dD_free_xy = expand_rows(dD_free_xy,free_idx,N)

dD_free_yx = weight_matrix(nodes[free_idx],nodes,diffs_yx,coeffs=coeffs_yx,n=n,order=order)
dD_free_yx = expand_rows(dD_free_yx,free_idx,N)

dD_free_yy = weight_matrix(nodes[free_idx],nodes,diffs_yy,coeffs=coeffs_yy,n=n,order=order)
dD_free_yy = expand_rows(dD_free_yy,free_idx,N)

# stack them together
dD_free_x = scipy.sparse.hstack((dD_free_xx,dD_free_xy))
dD_free_y = scipy.sparse.hstack((dD_free_yx,dD_free_yy))
dD_free = scipy.sparse.vstack((dD_free_x,dD_free_y))

# combine the PDE and the boundary conditions 
G = D + dD_fix + dD_free
G = G.tocsc()
plt.imshow(np.abs(G.A)>0.0)
plt.show()

d_x = np.zeros((N,))
d_y = np.zeros((N,))

d_x[interior_and_ghosts_idx] = 0.0
d_x[free_idx] = 0.0
d_x[fixed_idx] = 0.0

d_y[interior_and_ghosts_idx] = body_force
d_y[free_idx] = 0.0
d_y[fixed_idx] = 0.0

d = np.hstack((d_x,d_y))


import scipy.sparse as sp
def GaussSeidel(A,d,m=None,iter=10):
    if m is None:
        m = np.zeros_like(d)

    A = sp.csc_matrix(A,dtype=np.float64,copy=False)
    L = sp.tril(A).tocsr()
    U = sp.triu(A,k=1).tocsr()
    for i in range(iter):
        m = spla.spsolve_triangular(L,d - U.dot(m),lower=True)

    return m

def callback(res,_itr=[0]):
  l2 = np.linalg.norm(res)
  print('residual on iteration %s: %s' % (_itr[0],l2))
  _itr[0] += 1
  return 

print('computing incomplete LU decomposition')
print(np.min(np.abs(G.diagonal())))
#lu = spla.splu(G)
#M = spla.LinearOperator((2*N,2*N),lu.solve)
u = scipy.sparse.linalg.spsolve(G,d)
#print('exited with info: %s' % info)

# reshape the solution
u = np.reshape(u,(2,-1))
u_x,u_y = u
## Calculate strain from displacements
D_x = weight_matrix(nodes,nodes,(1,0),n=n)
D_y = weight_matrix(nodes,nodes,(0,1),n=n)
e_xx = D_x.dot(u_x)
e_yy = D_y.dot(u_y)
e_xy = 0.5*(D_y.dot(u_x) + D_x.dot(u_y))
# calculate second strain invariant
I2 = np.sqrt(e_xx**2 + e_yy**2 + 2*e_xy**2)

## Plot the results
#####################################################################
# toss out ghost nodes
g = len(free_idx)
nodes = nodes[interior_and_boundary_idx]
u_x,u_y = u_x[interior_and_boundary_idx],u_y[interior_and_boundary_idx]
I2 = I2[interior_and_boundary_idx]

fig,ax = plt.subplots(figsize=(7,3.5))
# plot the fixed boundary
ax.plot(vert[smp[0],0],vert[smp[0],1],'r-',lw=2,label='fixed',zorder=1)
# plot the free boundary
ax.plot(vert[smp[1],0],vert[smp[1],1],'r--',lw=2,label='free',zorder=1)
for s in smp[2:]:
  ax.plot(vert[s,0],vert[s,1],'r--',lw=2,zorder=1)

# plot the second strain invariant
p = ax.tripcolor(nodes[:,0],nodes[:,1],I2,
                 norm=LogNorm(vmin=0.1,vmax=3.2),
                 cmap='viridis',zorder=0)
# plot the displacement vectors
ax.quiver(nodes[:,0],nodes[:,1],u_x,u_y,zorder=2)
ax.set_xlim((-0.1,2.1))
ax.set_ylim((-0.25,1.1))
ax.set_aspect('equal')
ax.legend(loc=3,frameon=False,fontsize=12,ncol=2)
cbar = fig.colorbar(p)
cbar.set_label('second strain invariant')
fig.tight_layout()
plt.savefig('../figures/fd.b.png')
plt.show() 
