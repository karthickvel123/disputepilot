import React, { useEffect, useRef, useState } from 'react';
import {
  Activity,
  Bell,
  ClipboardList,
  History,
  LayoutDashboard,
  LogOut,
  Settings,
  Shield,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';
import { getNotifications, markNotificationRead } from '../api';

const navigationItems = [
  { id: 'dashboard', label: 'Overview', icon: LayoutDashboard },
  { id: 'disputes', label: 'Dispute worklist', icon: ClipboardList },
  { id: 'review-queue', label: 'Review queue', icon: ShieldCheck },
  { id: 'audit', label: 'Audit ledger', icon: History },
  { id: 'settings', label: 'Settings', icon: Settings },
];

function Brand() {
  return (
    <div className="brand-lockup">
      <span className="brand-mark"><Shield className="h-5 w-5" /></span>
      <span>
        <span className="brand-name">DisputePilot</span>
        <span className="brand-caption">MERCHANT OPERATIONS</span>
      </span>
    </div>
  );
}

export default function Navbar({
  activeTab,
  setActiveTab,
  user,
  userRole = 'reviewer',
  onLogout,
  systemSettings,
  isDemoAllowed = false,
  isSimMode = false,
  onOpenLanding,
  onOpenLogin,
  onQuickDemoLogin,
  onSimulateDispute,
  onSelectCase,
}) {
  const isSim = isSimMode || systemSettings?.data_mode === 'sim';
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationError, setNotificationError] = useState('');
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef(null);

  useEffect(() => {
    if (!user) {
      setNotifications([]);
      setUnreadCount(0);
      return undefined;
    }

    loadNotifications();
    const interval = window.setInterval(loadNotifications, 45000);
    return () => window.clearInterval(interval);
  }, [user]);

  useEffect(() => {
    function handleClickOutside(event) {
      if (notifRef.current && !notifRef.current.contains(event.target)) {
        setNotifOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  async function loadNotifications() {
    try {
      const data = await getNotifications();
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
      setNotificationError('');
    } catch (error) {
      setNotificationError(error.message || 'Notifications could not be loaded.');
    }
  }

  async function handleNotificationClick(notification) {
    try {
      await markNotificationRead(notification.id);
      setNotifications((previous) => previous.filter((item) => item.id !== notification.id));
      setUnreadCount((count) => Math.max(0, count - 1));
      setNotificationError('');
      setNotifOpen(false);
      if (notification.case_id) {
        onSelectCase(notification.case_id);
      }
    } catch (error) {
      setNotificationError(error.message || 'The notification could not be marked as read.');
    }
  }

  function renderNavigation(mobile = false) {
    return navigationItems.map(({ id, label, icon: Icon }) => {
      const selected = activeTab === id || (id === 'disputes' && activeTab === 'detail');
      return (
        <button
          key={id}
          id={`nav-${id}${mobile ? '-mobile' : ''}`}
          type="button"
          onClick={() => setActiveTab(id)}
          aria-current={selected ? 'page' : undefined}
          className={`app-nav-link${selected ? ' is-active' : ''}${mobile ? ' is-mobile' : ''}`}
        >
          <Icon className="h-4 w-4" />
          <span>{label}</span>
          {id === 'review-queue' && <span className="nav-link-indicator" aria-hidden="true" />}
        </button>
      );
    });
  }

  function renderNotifications() {
    return (
      <div className="notification-anchor" ref={notifRef}>
        <button
          id="btn-notifications"
          type="button"
          onClick={() => setNotifOpen((open) => !open)}
          aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}
          aria-expanded={notifOpen}
          className="notification-trigger"
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && <span className="notification-count">{unreadCount > 9 ? '9+' : unreadCount}</span>}
        </button>
        {notifOpen && (
          <section className="notification-menu" aria-label="Notifications">
            <div className="notification-menu-heading">
              <div>
                <p className="notification-title">Notifications</p>
                <p className="notification-caption">Action items for your team</p>
              </div>
              <button type="button" className="icon-button" aria-label="Close notifications" onClick={() => setNotifOpen(false)}>
                <X className="h-4 w-4" />
              </button>
            </div>
            {notificationError && <p className="notification-error">{notificationError}</p>}
            <div className="notification-list">
              {notifications.length === 0 ? (
                <p className="notification-empty">You’re all caught up.</p>
              ) : notifications.map((notification) => (
                <button
                  key={notification.id}
                  type="button"
                  onClick={() => handleNotificationClick(notification)}
                  className="notification-item"
                >
                  <span className={`notification-dot is-${notification.type || 'info'}`} />
                  <span className="notification-item-copy">
                    <span className="notification-item-title">{notification.title}</span>
                    <span className="notification-item-message">{notification.message}</span>
                    {notification.case_id && <span className="notification-case">Open case {notification.case_id}</span>}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    );
  }

  const modeLabel = isSim ? 'Simulation environment' : 'Live environment';

  if (!user) {
    return (
      <header className="guest-header">
        <button type="button" className="brand-button" onClick={onOpenLanding} aria-label="DisputePilot home">
          <Brand />
        </button>
        <nav className="guest-nav-links" aria-label="Page sections">
          <a href="#approach">Our approach</a>
          <a href="#security">Security</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="guest-header-actions">
          <span className={`environment-label${isSim ? ' is-simulation' : ''}`}>
            <span className="environment-dot" />
            {modeLabel}
          </span>
          {onQuickDemoLogin && (
            <button id="btn-nav-quick-demo" type="button" onClick={onQuickDemoLogin} className="btn btn-primary guest-demo-button">
              <Sparkles className="h-4 w-4" />
              <span>Launch Demo</span>
            </button>
          )}
          <button id="btn-launch-login" type="button" onClick={onOpenLogin || (() => setActiveTab('dashboard'))} className="btn btn-secondary guest-signin-button">
            Sign in
          </button>
        </div>
      </header>
    );
  }

  return (
    <>
      <aside className="app-sidebar">
        <button type="button" className="brand-button" onClick={onOpenLanding} aria-label="DisputePilot home">
          <Brand />
        </button>

        <div className="sidebar-section-label">WORKSPACE</div>
        <nav className="sidebar-navigation" aria-label="Main navigation">
          {renderNavigation()}
        </nav>

        <div className={`sidebar-environment${isSim ? ' is-simulation' : ''}`}>
          <span className="environment-dot" />
          <span>
            <span className="environment-name">{isSim ? 'Simulation mode' : 'Live environment'}</span>
            <span className="environment-caption">{isSim ? 'Synthetic case data' : 'Connected to Razorpay'}</span>
          </span>
        </div>

        {onSimulateDispute && (
          <button id="btn-sidebar-simulate" type="button" onClick={onSimulateDispute} className="sidebar-simulate">
            <Zap className="h-4 w-4" />
            <span>Simulate a dispute</span>
          </button>
        )}

        <div className="sidebar-user">
          <span className="sidebar-avatar">{user.charAt(0).toUpperCase()}</span>
          <span className="sidebar-user-copy">
            <span className="sidebar-user-name">{user}</span>
            <span className="sidebar-user-role">{userRole}</span>
          </span>
          <button id="btn-logout" type="button" onClick={onLogout} className="icon-button sidebar-logout" aria-label="Sign out" title="Sign out">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </aside>

      <div className="mobile-navigation">
        <header className="mobile-header">
          <button type="button" className="brand-button" onClick={onOpenLanding} aria-label="DisputePilot home">
            <Brand />
          </button>
          <div className="mobile-header-actions">
            {onSimulateDispute && (
              <button id="btn-mobile-simulate" type="button" onClick={onSimulateDispute} className="icon-button" aria-label="Simulate a dispute">
                <Zap className="h-4 w-4" />
              </button>
            )}
            {renderNotifications()}
            <button id="btn-mobile-logout" type="button" onClick={onLogout} className="icon-button" aria-label="Sign out">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>
        <nav className="mobile-navigation-links" aria-label="Main navigation">
          {renderNavigation(true)}
        </nav>
      </div>

      <div className="desktop-topbar">
        <div className="topbar-context">
          <Activity className="h-4 w-4" />
          <span>Merchant defense workspace</span>
        </div>
        <div className="topbar-actions">
          <span className={`environment-label${isSim ? ' is-simulation' : ''}`}>
            <span className="environment-dot" />
            {modeLabel}
          </span>
          {renderNotifications()}
          <span className="topbar-divider" />
          <span className="topbar-user">{user}</span>
        </div>
      </div>
    </>
  );
}
