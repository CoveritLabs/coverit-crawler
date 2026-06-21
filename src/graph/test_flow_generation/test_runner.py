import asyncio
import random
import logging
import time
from test_flow_gen import find_all_flows  

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class MockGraphRepo:
    def __init__(self, target_nodes: int = 20, max_branches: int = 3):
        self.target_nodes = target_nodes
        self.max_branches = max_branches
        self.raw_data = {}

    async def get_lightweight_flow_graph(self, session_id: str) -> dict:
        states = [{"state_hash": "node_0", "first_seen": 0, "is_checkpoint": True}]
        transitions = []
        t_id = 1
        
        # 1. Guarantee every node is reachable by connecting it to a previous node
        for i in range(1, self.target_nodes):
            node_name = f"node_{i}"
            states.append({"state_hash": node_name, "first_seen": i, "is_checkpoint": random.random() < 0.3})
            
            src = f"node_{random.randint(0, i-1)}"
            transitions.append({
                "source_hash": src,
                "target_hash": node_name,
                "transition_id": f"t_{t_id}"
            })
            t_id += 1
            
        # 2. Add extra random branches/cycles to build complexity
        node_pool = [f"node_{i}" for i in range(self.target_nodes)]
        for src in node_pool:
            extra_branches = random.randint(0, self.max_branches - 1)
            for _ in range(extra_branches):
                tgt = random.choice(node_pool)
                transitions.append({
                    "source_hash": src,
                    "target_hash": tgt,
                    "transition_id": f"t_{t_id}"
                })
                t_id += 1
                
        self.raw_data = {"states": states, "transitions": transitions}
        return self.raw_data

def print_graphviz_dot(raw: dict):
    print("\n--- COPY AND PASTE THIS INTO: https://dreampuf.github.io/GraphvizOnline/ ---")
    print("digraph G {")
    print('  rankdir="LR";')
    print('  node [style=filled, fillcolor=lightblue];')
    
    for t in raw.get("transitions", []):
        src = t["source_hash"]
        tgt = t["target_hash"]
        tid = t["transition_id"]
        print(f'  "{src}" -> "{tgt}" [label="{tid}"];')
    print("}\n-------------------------------------------------------------------------")

async def main():
    repo = MockGraphRepo(target_nodes=1000, max_branches=5)
    
   
    start_time = time.time()
    selected_flows = await find_all_flows(
        graph_repo=repo,
        session_id="mock_session_123",
        min_num_of_states_per_tf=4,
        max_num_of_states_per_tf=20,
        convergence_threshold=0.0
    )
    end_time = time.time()
    print(f"\nTime taken to find all flows: {end_time - start_time:.4f} seconds")
    
    print_graphviz_dot(repo.raw_data)
    
    print(f"\nPipeline returned {len(selected_flows)} highly optimized TestFlows:")
    for i, tf in enumerate(selected_flows):
        # Build an alternating chain of: node -> [edge] -> node
        path_elements = [tf.node_path[0]]
        for edge_id, next_node in zip(tf.transition_ids, tf.node_path[1:]):
            path_elements.append(f" -> [{edge_id}] -> {next_node}")
        
        full_visual_path = "".join(path_elements)
        
        print(f"\n Flow {i} (Edges: {len(tf.transition_ids)}, States: {len(tf.node_path)}):")
        print(f"    {full_visual_path}")

if __name__ == "__main__":
    asyncio.run(main())