/**
 * PerformanceDashboard — visible to MIS Manager / Supervisor / Admin.
 * Shows per-officer ticket stats, dept manager throughput, and overall summary.
 */
import { useEffect, useState } from 'react';
import {
  Alert, Box, Chip, CircularProgress,
  LinearProgress, Paper, Stack, Table,
  TableBody, TableCell, TableHead, TableRow, Typography,
} from '@mui/material';
import {
  AssignmentOutlined, CheckCircleOutlined,
  HourglassEmptyOutlined, PersonOutlined, WarningAmberOutlined,
} from '@mui/icons-material';
import { usersAPI } from '../../api/users';

type PerfData = {
  summary: { total: number; closed: number; pending: number; unassigned: number };
  officers: { id: number; full_name: string | null; email: string; role_name: string | null; total: number; completed: number; pending: number; in_progress: number }[];
  dept_managers: { id: number; full_name: string | null; email: string; total: number; pending: number; closed: number }[];
};

const pct = (n: number, d: number) => (d === 0 ? 0 : Math.round((n / d) * 100));

function SummaryCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: number; color: string }) {
  return (
    <Paper sx={{ p: 2.5, borderTop: `3px solid ${color}`, flex: 1, minWidth: 140 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, color }}>
        {icon}
        <Typography variant="caption" fontWeight={700} sx={{ color, letterSpacing: .6, textTransform: 'uppercase', fontSize: 10 }}>
          {label}
        </Typography>
      </Box>
      <Typography sx={{ fontSize: 34, fontWeight: 800, color, lineHeight: 1 }}>{value}</Typography>
    </Paper>
  );
}

export function PerformanceDashboard() {
  const [data, setData]       = useState<PerfData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState('');

  useEffect(() => {
    usersAPI.performance()
      .then((r) => setData(r.data))
      .catch(() => setError('Unable to load performance data'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', pt: 8 }}><CircularProgress /></Box>;
  if (error)   return <Alert severity="error">{error}</Alert>;
  if (!data)   return null;

  const { summary, officers, dept_managers } = data;
  const closureRate = pct(summary.closed, summary.total);

  return (
    <Stack spacing={3}>
      {/* page header */}
      <Box>
        <Typography variant="h5" fontWeight={700}>Performance Overview</Typography>
        <Typography color="text.secondary" variant="body2">
          Live ticket metrics across the MIS team and business departments.
        </Typography>
      </Box>

      {/* summary cards */}
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <SummaryCard icon={<AssignmentOutlined fontSize="small" />}  label="Total tickets"  value={summary.total}      color="#7B1235" />
        <SummaryCard icon={<CheckCircleOutlined fontSize="small" />}  label="Closed"         value={summary.closed}     color="#2e6b57" />
        <SummaryCard icon={<HourglassEmptyOutlined fontSize="small" />} label="Pending"     value={summary.pending}    color="#a06b32" />
        <SummaryCard icon={<WarningAmberOutlined fontSize="small" />} label="Unassigned"    value={summary.unassigned} color="#b85c00" />
      </Box>

      {/* closure rate bar */}
      <Paper sx={{ p: 2.5 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="body2" fontWeight={600}>Overall closure rate</Typography>
          <Typography variant="body2" fontWeight={700} color="#2e6b57">{closureRate}%</Typography>
        </Box>
        <LinearProgress
          variant="determinate"
          value={closureRate}
          sx={{ height: 8, borderRadius: 4, bgcolor: '#e8e0e4', '& .MuiLinearProgress-bar': { bgcolor: '#2e6b57' } }}
        />
        <Typography variant="caption" color="text.secondary" sx={{ mt: .5, display: 'block' }}>
          {summary.closed} closed out of {summary.total} total tickets
        </Typography>
      </Paper>

      {/* MIS officer breakdown */}
      <Paper>
        <Box sx={{ px: 2.5, py: 2, borderBottom: '1px solid #e6e0dc', display: 'flex', alignItems: 'center', gap: 1 }}>
          <PersonOutlined sx={{ color: '#7B1235' }} />
          <Typography variant="h6" fontWeight={700}>MIS Officer Performance</Typography>
        </Box>
        {officers.length === 0 ? (
          <Box sx={{ p: 3 }}><Typography color="text.secondary">No MIS Officers found.</Typography></Box>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow sx={{ '& th': { fontWeight: 700, color: '#5a4a50', fontSize: 12, letterSpacing: .4, bgcolor: '#faf7f5' } }}>
                <TableCell>Officer</TableCell>
                <TableCell align="center">Total</TableCell>
                <TableCell align="center">In Progress</TableCell>
                <TableCell align="center">Pending</TableCell>
                <TableCell align="center">Completed</TableCell>
                <TableCell align="center">Completion rate</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {officers.map((o) => (
                <TableRow key={o.id} hover>
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>{o.full_name ?? o.email}</Typography>
                    <Typography variant="caption" color="text.secondary">{o.role_name}</Typography>
                  </TableCell>
                  <TableCell align="center">
                    <Chip label={o.total} size="small" sx={{ fontWeight: 700 }} />
                  </TableCell>
                  <TableCell align="center">
                    <Chip label={o.in_progress} size="small" color={o.in_progress > 0 ? 'primary' : 'default'} />
                  </TableCell>
                  <TableCell align="center">
                    <Chip label={o.pending} size="small" color={o.pending > 3 ? 'warning' : 'default'} />
                  </TableCell>
                  <TableCell align="center">
                    <Chip label={o.completed} size="small" color={o.completed > 0 ? 'success' : 'default'} />
                  </TableCell>
                  <TableCell align="center" sx={{ minWidth: 140 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <LinearProgress
                        variant="determinate"
                        value={pct(o.completed, o.total)}
                        sx={{ flex: 1, height: 6, borderRadius: 3, bgcolor: '#e8e0e4', '& .MuiLinearProgress-bar': { bgcolor: '#2e6b57' } }}
                      />
                      <Typography variant="caption" fontWeight={700} sx={{ minWidth: 30 }}>
                        {pct(o.completed, o.total)}%
                      </Typography>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      {/* Department manager breakdown */}
      {dept_managers.length > 0 && (
        <Paper>
          <Box sx={{ px: 2.5, py: 2, borderBottom: '1px solid #e6e0dc' }}>
            <Typography variant="h6" fontWeight={700}>Department Manager Throughput</Typography>
            <Typography variant="caption" color="text.secondary">Tickets submitted from each department</Typography>
          </Box>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ '& th': { fontWeight: 700, color: '#5a4a50', fontSize: 12, bgcolor: '#faf7f5' } }}>
                <TableCell>Manager</TableCell>
                <TableCell align="center">Total submitted</TableCell>
                <TableCell align="center">Pending</TableCell>
                <TableCell align="center">Closed</TableCell>
                <TableCell align="center">Completion rate</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {dept_managers.map((m) => (
                <TableRow key={m.id} hover>
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>{m.full_name ?? m.email}</Typography>
                  </TableCell>
                  <TableCell align="center"><Chip label={m.total} size="small" sx={{ fontWeight: 700 }} /></TableCell>
                  <TableCell align="center"><Chip label={m.pending} size="small" color={m.pending > 3 ? 'warning' : 'default'} /></TableCell>
                  <TableCell align="center"><Chip label={m.closed} size="small" color={m.closed > 0 ? 'success' : 'default'} /></TableCell>
                  <TableCell align="center" sx={{ minWidth: 140 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <LinearProgress
                        variant="determinate"
                        value={pct(m.closed, m.total)}
                        sx={{ flex: 1, height: 6, borderRadius: 3, bgcolor: '#e8e0e4', '& .MuiLinearProgress-bar': { bgcolor: '#7B1235' } }}
                      />
                      <Typography variant="caption" fontWeight={700} sx={{ minWidth: 30 }}>
                        {pct(m.closed, m.total)}%
                      </Typography>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Stack>
  );
}
