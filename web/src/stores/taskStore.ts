import { create } from 'zustand';
import { api } from '../api/client';

export interface Task {
  id: string;
  title: string;
  status: string;
  deadline: string | null;
  source: string;
  source_url: string | null;
  created_at: string;
  updated_at: string;
  content?: string;
}

interface TaskState {
  tasks: Task[];
  filter: string;
  searchQuery: string;
  loading: boolean;
  showCreateDialog: boolean;

  // Detail view
  selectedTask: Task | null;
  detailLoading: boolean;
  saving: boolean;

  loadTasks: () => Promise<void>;
  setFilter: (f: string) => void;
  setSearch: (q: string) => void;
  updateStatus: (id: string, status: string) => Promise<void>;
  createTask: (title: string, content: string, deadline: string) => Promise<void>;
  setShowCreateDialog: (show: boolean) => void;

  loadTask: (id: string) => Promise<void>;
  saveTaskContent: (id: string, content: string) => Promise<void>;
  clearSelectedTask: () => void;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: [],
  filter: '',
  searchQuery: '',
  loading: true,
  showCreateDialog: false,

  selectedTask: null,
  detailLoading: false,
  saving: false,

  loadTasks: async () => {
    try {
      const { filter, searchQuery } = get();
      const { tasks } = searchQuery
        ? await api.searchTasks(searchQuery, filter || undefined)
        : await api.listTasks(filter || undefined);
      set({ tasks, loading: false });
    } catch (e) {
      console.error('Failed to load tasks:', e);
      set({ loading: false });
    }
  },

  setFilter: (f: string) => {
    set({ filter: f });
    get().loadTasks();
  },

  setSearch: (q: string) => {
    set({ searchQuery: q });
    get().loadTasks();
  },

  updateStatus: async (id: string, status: string) => {
    await api.updateTask(id, { status });
    // Update selected task inline if viewing it
    const sel = get().selectedTask;
    if (sel && sel.id === id) {
      set({ selectedTask: { ...sel, status } });
    }
    get().loadTasks();
  },

  createTask: async (title: string, content: string, deadline: string) => {
    await api.createTask({ title, content, deadline });
    set({ showCreateDialog: false });
    get().loadTasks();
  },

  setShowCreateDialog: (show: boolean) => set({ showCreateDialog: show }),

  loadTask: async (id: string) => {
    set({ detailLoading: true, selectedTask: null });
    try {
      const task = await api.getTask(id);
      set({ selectedTask: task, detailLoading: false });
    } catch (e) {
      console.error('Failed to load task:', e);
      set({ detailLoading: false });
    }
  },

  saveTaskContent: async (id: string, content: string) => {
    set({ saving: true });
    try {
      await api.updateTask(id, { content });
      // Update local state
      const sel = get().selectedTask;
      if (sel && sel.id === id) {
        set({ selectedTask: { ...sel, content } });
      }
    } catch (e) {
      console.error('Failed to save task:', e);
    } finally {
      set({ saving: false });
    }
  },

  clearSelectedTask: () => set({ selectedTask: null }),
}));
