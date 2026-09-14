set terminal pdfcairo enhanced color size 10in,4.4in font 'Helvetica,11'
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
set output 'plots/team-law-predictions.pdf'
set multiplot layout 1,2 title 'Frozen lab-only Kuethe--Lee laws (no Hazel observations)' font ',15' margins 0.08,0.98,0.14,0.90 spacing 0.10,0.05
set xrange [2013:2030]
set xlabel 'Introduction year'
set ylabel 'L2-like capacity (KiB)'
set logscale y 2
plot 'plot-data/lab-servers.dat' u 1:2:3:4 w yerrorlines lw 1.7 pt 7 ps 1.1 lc rgb 'black' title 'lab servers', future u 1:2 w l dt 2 lw 2.2 lc rgb 'black' title '2.79-year doubling'
unset logscale y
set ylabel 'Smallest visible spatial boundary (bytes)'
set yrange [56:72]
plot all u 1:16 w linespoints lw 1.7 pt 7 ps 1.0 lc rgb 'black' title '8 lab systems', future u 1:8 w l dt 2 lw 2.2 lc rgb 'black' title '64-byte forecast'
unset multiplot
