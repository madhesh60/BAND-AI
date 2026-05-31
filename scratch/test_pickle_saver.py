import pickle
import os
from collections import defaultdict
from langgraph.checkpoint.memory import MemorySaver

class PersistentMemorySaver(MemorySaver):
    def __init__(self, filepath: str = ".test_memory.pkl", **kwargs):
        super().__init__(**kwargs)
        self.filepath = filepath
        self._load()

    def _save(self):
        def to_dict_recursive(d):
            if isinstance(d, defaultdict):
                return {k: to_dict_recursive(v) for k, v in d.items()}
            return d

        data = {
            "storage": to_dict_recursive(self.storage),
            "writes": dict(self.writes),
            "blobs": dict(self.blobs),
        }
        with open(self.filepath, "wb") as f:
            pickle.dump(data, f)
        print("Saved!")

    def _load(self):
        if not os.path.exists(self.filepath):
            print("No filepath found to load")
            return
        with open(self.filepath, "rb") as f:
            data = pickle.load(f)
        
        self.storage = defaultdict(lambda: defaultdict(dict))
        for thread_id, ns_dict in data.get("storage", {}).items():
            for ns, cp_dict in ns_dict.items():
                for cp_id, cp_val in cp_dict.items():
                    self.storage[thread_id][ns][cp_id] = cp_val
        
        self.writes = defaultdict(dict)
        for k, v in data.get("writes", {}).items():
            self.writes[k] = v
            
        self.blobs = defaultdict(None)
        for k, v in data.get("blobs", {}).items():
            self.blobs[k] = v
        print("Loaded!")

# Test it
saver = PersistentMemorySaver()
saver.storage["thread-1"][""]["checkpoint-1"] = (b"checkpoint", b"metadata", None)
saver._save()

saver2 = PersistentMemorySaver()
print("Restored storage:", dict(saver2.storage))
print("Restored item:", saver2.storage["thread-1"][""]["checkpoint-1"])
