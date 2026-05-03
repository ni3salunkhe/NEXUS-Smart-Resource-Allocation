import { create } from 'zustand';
import { AppNotification } from '../types/notification.types';

interface NotificationStore {
  notifications: AppNotification[];
  unread_count: number;
  escalation_count: number;
  add: (notification: AppNotification) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  dismiss: (id: string) => void;
  clearAll: () => void;
}

export const useNotificationStore = create<NotificationStore>((set) => ({
  notifications: [],
  unread_count: 0,
  escalation_count: 0,

  add: (notification) =>
    set((state) => {
      const isEscalation = notification.event_type === 'alert.escalation';
      const updatedNotifications = [notification, ...state.notifications].slice(0, 200);
      return {
        notifications: updatedNotifications,
        unread_count: state.unread_count + 1,
        escalation_count: state.escalation_count + (isEscalation ? 1 : 0),
      };
    }),

  markRead: (id) =>
    set((state) => {
      const notif = state.notifications.find((n) => n.id === id);
      if (!notif || notif.read) return state;

      return {
        notifications: state.notifications.map((n) =>
          n.id === id ? { ...n, read: true } : n
        ),
        unread_count: Math.max(0, state.unread_count - 1),
      };
    }),

  markAllRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unread_count: 0,
    })),

  dismiss: (id) =>
    set((state) => {
      const notif = state.notifications.find((n) => n.id === id);
      if (!notif) return state;

      const isEscalation = notif.event_type === 'alert.escalation';
      return {
        notifications: state.notifications.filter((n) => n.id !== id),
        unread_count: notif.read ? state.unread_count : Math.max(0, state.unread_count - 1),
        escalation_count: isEscalation ? Math.max(0, state.escalation_count - 1) : state.escalation_count,
      };
    }),

  clearAll: () =>
    set((state) => {
      const escalations = state.notifications.filter(
        (n) => n.event_type === 'alert.escalation'
      );
      // Escalations are never evicted until explicitly resolved, normally
      return {
        notifications: escalations,
        unread_count: escalations.filter((n) => !n.read).length,
        escalation_count: escalations.length,
      };
    }),
}));
