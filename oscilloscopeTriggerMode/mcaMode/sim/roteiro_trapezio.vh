        fork : rot begin
            // tau = 20 us com passo de 160 ns: PZ = 4/(exp(0,16/20)-1) = 498; subida 12, topo 6; SH = 11
            #200000; comando(12, 12); #250000; comando(13, 6); #250000; comando(14, 498); #250000; comando(15, 11);
            #250000;  comando(11, 1);          // liga o filtro
            #250000;  comando(4, 1);           // modo picos (UART)
            #2700000; comando(7, 1);          // passa para UDP (entre dois pulsos)
            #2550000; comando(11, 0);         // desliga o filtro: volta a altura pelo pico 1-2-1
        end join
