#!/bin/sh
#SBATCH --job-name=sweep2-missing
#SBATCH --account=ewi-st-dis
#SBATCH --qos=medium 
#SBATCH --partition=general        # Request partition.
#SBATCH --exclude=influ[1-6],insy[15-16],awi[01-02]
#SBATCH --time=12:00:00            # Request run time (wall-clock). Default is 1 minute
#SBATCH --nodes=1                  # Request 1 node
#SBATCH --tasks-per-node=1         # Set one task per node
#SBATCH --gres=gpu:1               # Request 1 GPU
#SBATCH --mem=64G
#SBATCH --mail-type=END            # Set mail type to 'END' to receive a mail when the job finishes. %j is the Slurm jobId
#SBATCH --output=./output/slurm-%x-%j.out
#SBATCH --error=./output/slurm-%x-%j.err

# Increase file descriptor limit
ulimit -n 65536

# Assuming you have a dedicated directory for *.sif files
export APPTAINER_ROOT="/tudelft.net/staff-umbrella/ScalableGraphLearning/apptainer"
export APPTAINER_NAME="pytorch2.2.2-cuda11.8-ubuntu22.04-Federated.sif"


nvidia-smi

srun apptainer exec \
  --nv \
  -B /home/nfs/letouwen/megagnn_graphgym:/home/$USER/megagnn_graphgym \
  -B /tudelft.net/staff-umbrella/ScalableGraphLearning/lourens/data:/mnt/lourens/data \
  -B /tudelft.net/staff-umbrella/ScalableGraphLearning/lourens/exps/:/mnt/lourens/exps/results \
  $APPTAINER_ROOT/$APPTAINER_NAME \
  python -m MegaGNN.main --cfg configs/sweeps/increasing_FedAML-Large-HI-MegaGNN-PNA-base/increasing_16_FedAML-Large-HI-MegaGNN-PNA-base.yaml