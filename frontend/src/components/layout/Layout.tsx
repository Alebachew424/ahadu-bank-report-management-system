import { Link, Outlet } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { AssignmentOutlined, BarChartOutlined, ChatOutlined, DashboardOutlined, GroupsOutlined, HistoryOutlined, Logout, Menu, NotificationsNone, Add, RepeatOutlined } from '@mui/icons-material';
import { AppBar, Avatar, Box, Divider, Drawer, IconButton, List, ListItem, ListItemButton, ListItemIcon, ListItemText, Toolbar, Tooltip, Typography, useMediaQuery } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { authAPI } from '../../api/auth';

const drawerWidth = 256;

const MIS_MANAGER_ROLES = ['MIS Manager', 'MIS Supervisor', 'Admin', 'System Administrator'];

const Layout = () => {
  const navigate = useNavigate();
  const compact = useMediaQuery('(max-width:900px)');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [identity, setIdentity] = useState<{ full_name: string | null; email: string; role: string; permissions: string[]; is_superuser: boolean }>({ full_name: null, email: '', role: 'Requester', permissions: [], is_superuser: false });
  useEffect(() => {
    authAPI.me().then(({ data }) => {
      const permissions = Array.isArray(data.permissions) ? data.permissions : [];
      localStorage.setItem('user_permissions', JSON.stringify(permissions));
      setIdentity({ ...data, permissions, role: data.is_superuser ? 'System Administrator' : data.role_name || 'Requester' });
    }).catch(() => undefined);
  }, []);
  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_permissions');
    navigate('/login');
  };

  const can = (permission: string) => identity.is_superuser || (Array.isArray(identity.permissions) && (identity.permissions.includes('*') || identity.permissions.includes(permission)));
  const isMISManager = MIS_MANAGER_ROLES.includes(identity.role);

  const navigation = [
    { label: 'Overview',        icon: <DashboardOutlined />, path: '/' },
    { label: 'Ticket queue',    icon: <AssignmentOutlined />, path: '/requests' },
    ...(isMISManager ? [{ label: 'Performance',    icon: <BarChartOutlined />,   path: '/performance' }] : []),
    { label: 'Communications',  icon: <ChatOutlined />,       path: '/communications' },
    { label: 'Schedules',       icon: <RepeatOutlined />,     path: '/schedules' },
    ...(can('user:manage') ? [{ label: 'User management', icon: <GroupsOutlined />, path: '/users' }] : []),
    ...(can('user:manage') ? [{ label: 'Audit log',        icon: <HistoryOutlined />, path: '/audit' }] : []),
  ];

  const drawer = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ p: 3, pb: 2 }}>
        <Typography sx={{ color: '#fff', fontSize: 11, fontWeight: 700, letterSpacing: 1.5 }}>AHADU BANK</Typography>
        <Typography sx={{ color: 'rgba(255,255,255,.72)', fontSize: 12, mt: .5 }}>MIS SERVICE DESK</Typography>
      </Box>
      <Divider sx={{ borderColor: 'rgba(255,255,255,.14)' }} />
      <Box sx={{ px: 2, pt: 3 }}>
        <Typography sx={{ color: 'rgba(255,255,255,.5)', fontSize: 10, fontWeight: 700, letterSpacing: 1.2, px: 1.5, mb: 1 }}>WORKSPACE</Typography>
        <List disablePadding>
          {navigation.map((item) => (
            <ListItem key={item.path} disablePadding sx={{ mb: .5 }}>
              <ListItemButton component={Link} to={item.path} onClick={() => setDrawerOpen(false)} sx={{ color: 'rgba(255,255,255,.76)', borderRadius: 1, py: 1.15, '&:hover': { bgcolor: 'rgba(255,255,255,.1)', color: '#fff' } }}>
                <ListItemIcon sx={{ minWidth: 38, color: 'inherit' }}>{item.icon}</ListItemIcon>
                <ListItemText primary={item.label} slotProps={{ primary: { sx: { fontSize: 14, fontWeight: 600 } } }} />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </Box>
      <Box sx={{ mt: 'auto', p: 2 }}>
        <Divider sx={{ borderColor: 'rgba(255,255,255,.14)', mb: 2 }} />
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 1 }}>
          <Avatar sx={{ width: 34, height: 34, bgcolor: '#d7a45d', color: '#3a101f', fontSize: 14 }}>{(identity.full_name || identity.email || 'U').slice(0, 1).toUpperCase()}</Avatar>
          <Box sx={{ minWidth: 0 }}><Typography noWrap sx={{ color: '#fff', fontSize: 13, fontWeight: 700 }}>{identity.full_name || identity.email || 'Signed-in user'}</Typography><Typography sx={{ color: 'rgba(255,255,255,.55)', fontSize: 11 }}>{identity.role}</Typography></Box>
          <Tooltip title="Sign out"><IconButton onClick={logout} size="small" sx={{ ml: 'auto', color: 'rgba(255,255,255,.7)' }}><Logout fontSize="small" /></IconButton></Tooltip>
        </Box>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: '#f6f4f1' }}>
      <Drawer variant={compact ? 'temporary' : 'permanent'} open={compact ? drawerOpen : true} onClose={() => setDrawerOpen(false)} sx={{ '& .MuiDrawer-paper': { width: drawerWidth, boxSizing: 'border-box', bgcolor: '#7B1235', color: '#fff', border: 0 } }}>
        {drawer}
      </Drawer>
      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, ml: { xs: 0, md: `${drawerWidth}px` } }}>
        <AppBar position="sticky" elevation={0} sx={{ bgcolor: '#fff', color: '#241b1e', borderBottom: '1px solid #e6e0dc' }}>
          <Toolbar sx={{ minHeight: 70, px: { xs: 2, md: 4 } }}>
            {compact && <IconButton onClick={() => setDrawerOpen(true)} sx={{ mr: 1 }}><Menu /></IconButton>}
            <Box sx={{ flexGrow: 1 }}><Typography sx={{ fontSize: 12, color: '#7B1235', fontWeight: 700, letterSpacing: .7 }}>REPORT MANAGEMENT SYSTEM</Typography><Typography sx={{ fontSize: 12, color: '#81767a' }}>Operations workspace</Typography></Box>
            <Tooltip title="Notifications"><IconButton><NotificationsNone /></IconButton></Tooltip>
            <Tooltip title="Create ticket"><IconButton onClick={() => navigate('/requests/create')} sx={{ ml: 1, bgcolor: '#7B1235', color: '#fff', '&:hover': { bgcolor: '#5f0d29' } }}><Add /></IconButton></Tooltip>
          </Toolbar>
        </AppBar>
        <Box sx={{ maxWidth: 1440, mx: 'auto', p: { xs: 2, md: 4 } }}><Outlet /></Box>
      </Box>
    </Box>
  );
};

export default Layout;
