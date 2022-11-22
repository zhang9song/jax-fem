import jax
import jax.numpy as np
import numpy as onp
import os
import glob
import matplotlib.pyplot as plt

from jax_am.fem.solver import solver
from jax_am.fem.generate_mesh import Mesh, box_mesh, get_meshio_cell_type
from jax_am.fem.utils import save_sol

from applications.fem.crystal_plasticity.models import CrystalPlasticity

os.environ["CUDA_VISIBLE_DEVICES"] = "3"


data_dir = os.path.join(os.path.dirname(__file__), 'data')
numpy_dir = os.path.join(data_dir, 'numpy')
vtk_dir = os.path.join(data_dir, 'vtk')
csv_dir = os.path.join(data_dir, 'csv')


# Latex style plot
plt.rcParams.update({
    "text.latex.preamble": r"\usepackage{amsmath}",
    "text.usetex": True,
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica"]})


def problem():
    # ele_type = 'tetrahedron'
    # lag_order = 2

    ele_type = 'hexahedron'
    lag_order = 1

    # Nx, Ny, Nz = 2, 2, 20
    # Lx, Ly, Lz = 10., 10., 100.

    Nx, Ny, Nz = 1, 1, 1
    Lx, Ly, Lz = 1., 1., 1.

    cell_type = get_meshio_cell_type(ele_type, lag_order)
    meshio_mesh = box_mesh(Nx, Ny, Nz, Lx, Ly, Lz, data_dir, ele_type, lag_order)

    mesh = Mesh(meshio_mesh.points, meshio_mesh.cells_dict[cell_type])

    files = glob.glob(os.path.join(vtk_dir, f'*'))
    for f in files:
        os.remove(f)

    disps = np.linspace(0., 0.005, 11)
    ts = np.linspace(0., 0.5, 11)


    # forces = np.linspace(0., 200, 41)
    # ts = np.linspace(0., 1., 41)

    def corner(point):
        flag_x = np.isclose(point[0], 0., atol=1e-5)
        flag_y = np.isclose(point[1], 0., atol=1e-5)
        flag_z = np.isclose(point[2], 0., atol=1e-5)
        return np.logical_and(np.logical_and(flag_x, flag_y), flag_z)

    def bottom(point):
        return np.isclose(point[2], 0., atol=1e-5)

    def top(point):
        return np.isclose(point[2], Lz, atol=1e-5)

    def zero_dirichlet_val(point):
        return 0.

    def get_dirichlet_top(disp):
            def val_fn(point):
                return disp
            return val_fn

    def get_neumann_val(val):
        def neumann_val(point):
            return np.array([0., 0., val])
        return neumann_val


    # neumann_bc_info = [[top], [get_neumann_val(forces[0])]]

    dirichlet_bc_info = [[corner, corner, bottom, top], 
                         [0, 1, 2, 2], 
                         [zero_dirichlet_val, zero_dirichlet_val, zero_dirichlet_val, get_dirichlet_top(disps[0])]]

    # dirichlet_bc_info = [[corner, corner, bottom], 
    #                      [0, 1, 2], 
    #                      [zero_dirichlet_val]*3]


    problem = CrystalPlasticity(mesh, vec=3, dim=3, ele_type=ele_type, lag_order=lag_order, dirichlet_bc_info=dirichlet_bc_info)

    # problem = CrystalPlasticity(mesh, vec=3, dim=3, ele_type=ele_type, lag_order=lag_order, 
        # dirichlet_bc_info=dirichlet_bc_info, neumann_bc_info=neumann_bc_info)

    results_to_save = []

    sol = np.zeros((problem.num_total_nodes, problem.vec))

    for i in range(len(ts) - 1):
        problem.dt = ts[i + 1] - ts[i]
        print(f"\nStep {i + 1} in {len(ts) - 1}, disp = {disps[i + 1]}, dt = {problem.dt}")
        # print(f"\nStep {i + 1} in {len(ts) - 1}, force = {forces[i + 1]}, dt = {problem.dt}")

        dirichlet_bc_info[-1][-1] = get_dirichlet_top(disps[i + 1])
        problem.update_Dirichlet_boundary_conditions(dirichlet_bc_info)

        # problem.neumann_bc_info = [[top], [get_neumann_val(forces[i + 1])]]
        # problem.neumann = problem.compute_Neumann_integral()

        # sol = solver(problem, linear=False, initial_guess=sol)

        sol = solver(problem, linear=False)

        stress_zz = problem.compute_avg_stress(sol)
        F_p_zz, slip_resistance_0, slip_inc_dt_index_0 = problem.update_int_vars_gp(sol)
        print(f"stress_zz = {stress_zz}")
        
        vtk_path = os.path.join(data_dir, f'vtk/u_{i:03d}.vtu')
        save_sol(problem, sol, vtk_path, cell_type=cell_type)

        results_to_save.append([disps[i + 1]/Lz, F_p_zz, slip_resistance_0, slip_inc_dt_index_0, stress_zz])

    results_to_save = onp.array(results_to_save)

    os.makedirs(numpy_dir, exist_ok=True)
    onp.save(os.path.join(numpy_dir, 'jax_fem_out.npy'), results_to_save)
 

def plot_stress_strain():
    # time, e_zz, fp_zz, gss, pk2, slip_increment, stress_zz
    moose_out = onp.loadtxt(os.path.join(csv_dir, 'update_method_test_out.csv'), delimiter=',')

    # strain, fp_zz, gss, slip_increment, stress_zz
    jax_fem_out = onp.load(os.path.join(numpy_dir, 'jax_fem_out.npy'))

    fig = plt.figure(figsize=(8, 6))
    plt.plot(jax_fem_out[:, 0], moose_out[:, -1], label='MOOSE', color='blue', linestyle="-", linewidth=2)
    plt.plot(jax_fem_out[:, 0], jax_fem_out[:, -1], label='JAX-FEM', color='red', marker='o', markersize=8, linestyle='None') 
    plt.xlabel(r'Strain', fontsize=20)
    plt.ylabel(r'Stress [MPa]', fontsize=20)
    plt.tick_params(labelsize=18)
    plt.legend(fontsize=20, frameon=False)


if __name__ == "__main__":
    problem()
    # plot_stress_strain()
    # plt.show()