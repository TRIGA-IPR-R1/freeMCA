        fork : rot begin
            #300000;  comando(2, 0);          // sem média: 25 MSPS
            #250000;  comando(4, 2);          // modo contínuo
            #1200000; comando(9, 0);          // status no meio do fluxo
            #600000;  comando(2, 2);          // muda a taxa com o fluxo ligado: 6,25 MSPS
            #1500000; comando(4, 0);          // volta para formas por trigger (UART)
            #2500000; comando(4, 2);          // contínuo de novo: seq recomeça do zero
        end join
