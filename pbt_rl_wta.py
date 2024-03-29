import argparse
import os
import time
import numpy as np
from utils.mpi_utils import MPI_Tool
from stable_baselines3.common.evaluation import evaluate_policy
from utils.rl_tools import env_create_sb, env_create, eval_agent
# from pbt_toy import pbt_engine
from mpi4py import MPI
from stable_baselines3.common.results_plotter import load_results, ts2xy, plot_results
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
import gym
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback, StopTrainingOnRewardThreshold
import pandas as pd

mpi_tool = MPI_Tool()
from stable_baselines3.common.logger import configure
from torch.utils.tensorboard import SummaryWriter
#from tensorboardX import SummaryWriter

# Path to sb3 logger
tmp_path = "logs/sb3_logs/run_2"
models_dir = "logs/best_models"

checkpoint_callback = CheckpointCallback(
            save_freq=7000,
            save_path="logs/checkpoints",
            name_prefix="rl_model-checkpoint",
)
#best_reward_callback = SaveOnBestTrainingRewardCallback(1000, "monitor/best_model", True)

stop_training_callback = StopTrainingOnRewardThreshold(reward_threshold=50, verbose=1)

# Separate evaluation env (for bigfish)
eval_env = gym.make("procgen:procgen-bigfish-v0", num_levels=1, start_level=0,#render_mode="human", 
                        center_agent=False,distribution_mode="easy")
# Use deterministic actions for evaluation
eval_callback = EvalCallback(eval_env, best_model_save_path="logs/best_models",
                             log_path="logs/evaluations", eval_freq=5000,
                             callback_on_new_best=stop_training_callback,
                             deterministic=True, render=False)

def parse_args():
    # fmt: off
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp-name", type=str, default=os.path.basename(__file__).rstrip(".py"),
        help="the name of this experiment")
    parser.add_argument("--tb-writer", type=bool, default=False,
        help="if toggled, Tensorboard summary writer is enabled")
    
    # Algorithm specific arguments
    parser.add_argument("--env-id", type=str, default="Acrobot-v1",
        help="the id of the environment")
    parser.add_argument("--seed", type=int, default=141,
        help="seed of the experiment")
    parser.add_argument("--num-agents", type=int, default=1,
        help="number of agents")
    parser.add_argument("--total-generations", type=int, default=500,
        help="total generations of the experiments")
    parser.add_argument("--agent-training-steps", type=int, default=5000,
        help="total generations of the experiments")
    
    parser.add_argument("--learning-rate-range", type=tuple, default=(1e-4, 1e-3),
        help="the range of leanring rates among different agents")
    parser.add_argument("--gamma-range", type=tuple, default=(0.8, 0.99),
        help="the range of discount factors among different agents")
    args = parser.parse_args()

    return args

class SaveOnBestTrainingRewardCallback(BaseCallback):
    """
    Callback for saving a model (the check is done every ``check_freq`` steps)
    based on the training reward (in practice, we recommend using ``EvalCallback``).

    :param check_freq:
    :param log_dir: Path to the folder where the model will be saved.
      It must contains the file created by the ``Monitor`` wrapper.
    :param verbose: Verbosity level: 0 for no output, 1 for info messages, 2 for debug messages
    """
    def __init__(self, check_freq: int, log_dir: str, verbose: int = 1):
        super(SaveOnBestTrainingRewardCallback, self).__init__(verbose)
        self.check_freq = check_freq
        self.log_dir = log_dir
        self.save_path = os.path.join(log_dir, "best_model")
        self.best_mean_reward = -np.inf

    def _init_callback(self) -> None:
        # Create folder if needed
        if self.save_path is not None:
            os.makedirs(self.save_path, exist_ok=True)

    def _on_step(self) -> bool:
        if self.n_calls % self.check_freq == 0:

          # Retrieve training reward
          x, y = ts2xy(load_results(self.log_dir), "timesteps")
          if len(x) > 0:

              # Mean training reward over the last 100 episodes
              mean_reward = np.mean(y[-100:])
              #if self.verbose >= 1:
                #print(f"Num timesteps: {self.num_timesteps}")
                #print(f"Best mean reward: {self.best_mean_reward:.2f} - Last mean reward per episode: {mean_reward:.2f}")

              # New best model, you could save the agent here
              if mean_reward > self.best_mean_reward:
                  self.best_mean_reward = mean_reward
                  # Example for saving best model
                  if self.verbose >= 1:
                    print(f"Saving new best model with reward {mean_reward} to {self.save_path}")
                  self.model.save(self.save_path)

        return True


##############
## CALLBACK ##
##############

print('CREATING CALLBACK...')   

# Saving model to same directory as Monitor directory every 'check_freq' steps
best_reward_callback = SaveOnBestTrainingRewardCallback(check_freq=1000, log_dir = tmp_path)#=models_dir)  
    

# This is the one we use 
class rl_agent():
    def __init__(self, idx, env_name, learning_rate, gamma, log_dir = "./tmp/gym/", seed=141) -> None:
        self.idx = idx
        self.seed = seed
        self.score = 0 # For now just use reward per episode 
        self.length = 0 # For now just use length per episode 

        if env_name[0:8] == "MiniGrid":
            self.env = env_create(env_name, idx)
            #self.model = DQN("MlpPolicy", env = self.env, verbose=0, create_eval_env= False)
            self.model =  PPO("MlpPolicy", env=self.env, verbose=0, create_eval_env=False)
        elif env_name[0:7] == "BigFish" or env_name[0:7] == "bigfish":          
            self.env = env_create(env_name, idx) 
            self.model = PPO("CnnPolicy", env=self.env, verbose=0)  #, tensorboard_log="logs/tensorboard") #Verbose = 1 prints out all data :-)
        elif env_name[0:11] == "LunarLander":
            self.env = env_create(env_name, idx) 
            self.model =  PPO("MlpPolicy", env=self.env, verbose=0, create_eval_env=False)
        elif env_name[0:5] == "nasim": 
            self.env = env_create(env_name, idx)
            #self.model = DQN("MlpPolicy", env = self.env, verbose=0, create_eval_env= False)
            self.model =  PPO("MlpPolicy", env=self.env, verbose=0, create_eval_env=False)
        elif env_name[0:6] == "dm2gym":
            self.env = env_create(env_name, idx)
            #self.model = DQN("MlpPolicy", env = self.env, verbose=0, create_eval_env=True)
            self.model = PPO("MultiInputPolicy", env=self.env, verbose=0, create_eval_env=True)
        else:
            #self.model = DQN("MlpPolicy", env = env_name, verbose=0, create_eval_env=True)
            self.model =  PPO("MlpPolicy", env=env_name, verbose=0, create_eval_env=True)
        self.model.gamma = gamma
        self.model.learning_rate = learning_rate 
        self.log_dir = os.path.join(log_dir, str(idx))
        new_logger = configure(tmp_path, ["csv", "tensorboard"])
        self.model.set_logger(new_logger)
        

    def step(self, traing_step=2000, callback=None, vanilla=False, rmsprop=False, Adam=False):
        """one episode of RL"""

        # Callback that saves a checkpoint to the 'logs'-folder every 500 training steps 
        self.model.learn(total_timesteps=traing_step, callback=best_reward_callback)# callback = best_reward_callback)#, callback = eval_callback) #progress_bar=True)#, tb_log_name="PPO", callback=[checkpoint_callback, eval_callback],)

    def exploit(self, best_params):

        self.model.set_parameters(best_params) 
        

    def explore(self):
        """
        perturb hyperparaters with noise from a normal distribution
        """
        
        # LR 0.95 decay
        self.model.learning_rate=self.model.learning_rate*np.random.triangular(0.9, 0.95, 1.2)

        if self.model.gamma*np.random.uniform(0.9, 1.1)>=0.99:
            self.model.gamma = 0.99
        elif self.model.gamma*np.random.uniform(0.9, 1.1)<=0.8:
            self.model.gamma = 0.8
        else:
            self.model.gamma = self.model.gamma*np.random.uniform(0.9, 1.1)


    def eval(self, vanilla=True, return_episode_rewards=False):

        # Evaluate the agent

        if vanilla:
            if return_episode_rewards == True:
                eps_reward, eps_length = evaluate_policy(self.model, self.model.get_env(), n_eval_episodes=10, return_episode_rewards=True)
                mean_reward = np.mean(eps_reward)
                mean_length = np.mean(eps_length)
                self.length = mean_length
            else:
                mean_reward, std_reward = evaluate_policy(self.model, self.model.get_env(), n_eval_episodes=10)
        else:
            mean_reward = eval_agent(self.model, self.model.get_env())

        self.score =  mean_reward
        

    def update(self):
        """
        Just update the
        """

def workers_init(args):
    workers = []
    for idx in range(args.num_agents):
        # get learning rate, uniformly sampled on log scale
        _l_lb = np.log10(args.learning_rate_range[0])
        _l_ub = np.log10(args.learning_rate_range[1])
        if _l_ub >= _l_lb:       
            _lr = 10 ** np.random.uniform(low=_l_lb, high=_l_ub)
        else:
            raise Exception('Error in Learning Rate Range: Low bound shoud less that the Upper bound')
        
        # get discount factor, uniformly sampled 
        _g_lb = np.log10(args.gamma_range[0])
        _g_ub = np.log10(args.gamma_range[1])
        if _g_ub >= _g_lb:       
            _g = np.random.uniform(low=_g_lb, high=_g_ub)
        else:
            raise Exception('Error in Gamma Range: Low bound shoud less that the Upper bound')
        
        workers.append(rl_agent(idx=idx, env_name=args.env_id, learning_rate=_lr, gamma=_g)) 
    return workers

class base_population(object):
    def __init__(self):
        self.agents_pool = []

    def create(self, agent_list):
        self.agents_pool = agent_list

    def get_scores(self):
        return [worker.score for worker in self.agents_pool]
        # return score

        # Hoping to be able to call on this when we need to save the best model of the population
    def get_best_model(self):
        _best_id = self.get_best_agent()
        return self.agents_pool[_best_id] 

        # Looks like this one retrieves the id of the best model
    def get_best_agent(self):
        return self.get_scores().index(max(self.get_scores()))
            

    def get_best_score(self):
        # return max(self.get_scores())
        _best_id = self.get_best_agent()
        return self.agents_pool[_best_id].score
    

    def get_best_results(self):
        # return max(self.get_scores())
        _best_id = self.get_best_agent()
        return [self.agents_pool[_best_id].score, self.agents_pool[_best_id].length] 

    def get_best_agent_params(self):
        _best_id = self.get_best_agent()
        _best_agent = self.agents_pool[_best_id]
        params = _best_agent.model.get_parameters()

        return params

    @property
    def size(self):
        return int(len(self.agents_pool))


class base_engine(object):
    def __init__(self, tb_logger=True):
        self.best_score_population = 0
        if mpi_tool.is_master & (tb_logger):
            #self.tb_writer = SummaryWriter()
            self.tb_writer = SummaryWriter("log/writer")

            self.log = pd.DataFrame(columns = ['best_reward', 'best_length', 'num_episodes'])

        else:
            self.tb_writer = False

    def create_local(self, pbt_population):

        self.population = pbt_population
        self.best_params_population = self.population.get_best_agent_params()
        

    def run(self, steps=3, exploit=False, explore=False, agent_training_steps=500, return_episode_rewards=True): # Haled steps and doubled number of angents.
        print("Agents number: {} at rank {} on node {}".format(
            self.population.size, mpi_tool.rank, str(mpi_tool.node)))
        for i in range(steps):

            if mpi_tool.is_master:
                best_score_at_each_step = self.best_score_population
                best_params_at_each_step = self.best_params_population
            else:
                best_score_at_each_step = None
                best_params_at_each_step = None
            best_score_at_each_step = mpi_tool.bcast(
                best_score_at_each_step, root=0)
            best_params_at_each_step = mpi_tool.bcast(
                best_params_at_each_step, root=0)

            for worker in self.population.agents_pool:
                worker.step(traing_step=agent_training_steps, vanilla=True)  # one step of GD
                worker.eval(return_episode_rewards=return_episode_rewards)
            # Update best score to the whole population
            best_score_to_sent = self.population.get_best_score()
            best_results_to_sent = self.population.get_best_results()
            best_params_to_sent = self.population.get_best_agent_params()


            if return_episode_rewards:
                rec_best_results, best_score_rank = MPI.COMM_WORLD.allreduce((best_results_to_sent, mpi_tool.rank), op=MPI.MAXLOC)
                rec_best_score, rec_best_length = rec_best_results
            else:    
                rec_best_score, best_score_rank = MPI.COMM_WORLD.allreduce((best_score_to_sent, mpi_tool.rank), op=MPI.MAXLOC)
            
            if mpi_tool.rank == best_score_rank:
                best_params_population = best_params_to_sent
            else:
                best_params_population = None
            
            best_params_population = mpi_tool.bcast(best_params_to_sent, root=best_score_rank)
            
            if i % 1 == 0 and i!=0:
                for worker in self.population.agents_pool:
                    if explore and exploit:
                        if worker.score <= rec_best_score:

                            worker.exploit(best_params= best_params_population)
                            worker.explore()

                    else:
                        pass


            if mpi_tool.is_master:
                self.best_score_population = rec_best_score
                if return_episode_rewards:
                    self.best_length_population = rec_best_length
                self.best_params_population = best_params_population

                if (i+1) % 1 == 0 and i!=0:
                    if self.tb_writer:
                        self.tb_writer.add_scalar('Best_Score/PBT_Results', self.best_score_population, i)
    
                    if return_episode_rewards:
                        if self.tb_writer:
                            self.tb_writer.add_scalar('Length/PBT_Results', self.best_length_population, i)
                        print("At iteration {} the Best Pop Score is {} Best Length is {}".format(
                        i, self.best_score_population, self.best_length_population))
                        #print("Saving model with id: {}".format(self.population.get_best_agent()))
                        best_agent = self.population.get_best_model()

                        #print("Saving model with id: {}".format(best_agent.idx))

                        # saving
                        best_agent.model.save("{}/{}".format(models_dir, "yuh"))
            
                    else:
                        print("At iteration {} the Best Pop Score is {} and the best params are {}".format(
                        i, self.best_score_population, self.best_params_population, self))
    

def main():

    args = parse_args()
    run_name = f"{args.env_id}__{args.exp_name}__{args.seed}__{int(time.time())}"
    workers = workers_init(args)
    writer = args.tb_writer
    
    num_generations = args.total_generations
    agent_training_steps = args.agent_training_steps
    
    local_size, local_agent_inds = mpi_tool.split_size(len(workers))
    print("Agent Number of {} at rank {}".format(local_agent_inds, mpi_tool.rank))

    # Initializing a local population
    pbt_population = base_population()
    pbt_population.create(agent_list=[workers[i] for i in local_agent_inds])

    # PRINTING OUT THE ID'S FOR ALL THE AGENTS IN THE AGENT POOL -> THERE IS ONE AGENT PER THREAD :-)))))))))))))
    #for i in range(len(pbt_population.agents_pool)): # pbt population is the same as population!
     #   print("population has id: ", pbt_population.agents_pool[i].idx)

    # Initializing a local engin
    pbt_engine = base_engine(tb_logger=writer)
    pbt_engine.create_local(pbt_population=pbt_population)

    run1 = pbt_engine.run(steps=num_generations,exploit=True, explore=True, agent_training_steps=agent_training_steps)
    if mpi_tool.is_master:
        if writer:
            pbt_engine.tb_writer.close()

if __name__ == '__main__':
    since = time.time()
    main()
    time_elapsed = time.time()-since
    if mpi_tool.is_master:
        print("Total Run Time: {}".format(time_elapsed))
