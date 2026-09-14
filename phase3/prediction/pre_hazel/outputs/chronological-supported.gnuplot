set terminal pdfcairo enhanced color size 12in,8in font 'Helvetica,11'
set border lw 1.4 lc rgb 'black'
set tics out nomirror
set xrange [2013:2030]
set xtics 4
unset grid
set key opaque box samplen 1.5 spacing 0.9 font ',9'
intel='plot-data/lab-intel.dat'
amd='plot-data/lab-amd.dat'
arm='plot-data/lab-ampere.dat'
all='plot-data/lab-all.dat'
future='plot-data/future-models.dat'
set output 'plots/chronological-supported.pdf'
set multiplot layout 3,3 rowsfirst title 'ECE Phase-I chronology and lab-only forecasts (no Hazel results)' font ',15' margins 0.06,0.98,0.07,0.93 spacing 0.06,0.09
set xlabel 'Introduction year'
set ylabel 'L1-like capacity (KiB)'
set logscale y 2
plot all u 1:2:3:4 w yerrorlines lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:2 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:2 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:2 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:3 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'
unset logscale y
set ylabel 'L1 conditional ways'
plot all u 1:5 w linespoints lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:5 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:5 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:5 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:4 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'
set ylabel 'L1-like median (ns/access)'
plot all u 1:6:7:8 w yerrorlines lw 1.2 pt 0 lc rgb '#777777' title 'P5--P95', intel u 1:6 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:6 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:6 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:5 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'
set ylabel 'L2-like capacity (KiB)'
set logscale y 2
plot all u 1:9:10:11 w yerrorlines lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:9 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:9 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:9 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:2 w l dt 2 lw 2 lc rgb 'black' title 'server fit'
unset logscale y
set ylabel 'L2 conditional ways'
plot all u 1:12 w linespoints lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:12 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:12 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:12 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:6 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'
set ylabel 'LLC-like effective capacity (MiB)'
set logscale y 2
plot all u 1:13:14:15 w yerrorlines lw 1.2 pt 0 lc rgb '#777777' title 'lab bracket', intel u 1:13 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:13 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:13 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:7 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'
unset logscale y
set ylabel 'Visible boundary (bytes)'
set yrange [56:72]
plot all u 1:16 w linespoints lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:16 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:16 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:16 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:8 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'
auto=1
set autoscale y
set ylabel 'Software timing metric (%)'
plot all u 1:17:18:19 w yerrorlines lw 1.2 pt 0 lc rgb '#777777' title 'threshold range', intel u 1:17 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:17 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:17 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:9 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'
set ylabel 'Inclusion category'
set yrange [0.5:3.5]
set ytics ('inclusive' 1, 'exclusive/victim' 2, 'uncertain' 3)
plot all u 1:20 w linespoints lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:20 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:20 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:20 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm'
unset multiplot
