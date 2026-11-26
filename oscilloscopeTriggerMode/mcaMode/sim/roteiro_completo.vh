        fork : rot begin
            #5000000;  comando(4, 1);          // picos pela UART
            #4000000;  comando(7, 1);          // picos por UDP
            #3000000;  comando(4, 0);          // formas por UDP
            #3000000;  comando(5, 100); #250000; comando(6, 300);   // janela 100 + 1 + 300
            #2900000;  comando(0, 2000);       // limiar alto
            #4000000;  comando(0, 60); #250000; comando(2, 3);      // limiar 60, média de 8
            #3900000;  comando(5, 650);        // inválido (n_pre > 600)
            #300000;   comando(99, 1);         // registrador inexistente
            #250000;   manda_byte(8'hA5); manda_byte(8'h5A); manda_byte(8'd0); manda_byte(8'd0); manda_byte(8'd9); manda_byte(8'h00);  // checksum errado: ignorado
            #250000;   comando(7, 0); #250000; comando(4, 0);       // formas (401 amostras) pela UART
            #9500000;  comando(8, 0);          // pausa
            #2000000;  comando(8, 1); #250000; comando(10, 0);      // volta e zera o tempo
        end join
