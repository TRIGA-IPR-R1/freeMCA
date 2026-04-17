# freeMCA ⚛️☢️🔬

**Um Analisador Multicanal (MCA) Totalmente Livre para Detectores de Radiação Ionizante.**

O `freeMCA` é um projeto de código aberto e hardware livre que tem como objetivo projetar, construir e programar um Multi-Channel Analyzer (MCA) acessível para espectrometria de radiação, criando uma plataforma de pesquisa em instrumentação nuclear e desenvolvimento de produtos de baixo custo.



## Hardware

### FPGA Base
Para o desenvolvimento inicial, o projeto utiliza a placa **Colorlight i9plus-v6.1** (equipada com o FPGA Xilinx Artix-7 **XC7A50T-FGG484**). A escolha dessa plataforma baseia-se nas seguintes vantagens estratégicas:

* **Custo-Benefício:** Entrega alto poder de processamento lógico com um custo de aquisição muito baixo.
* **Recursos Lógicos:** Alta disponibilidade de pinos de I/O e células lógicas para processamento digital de sinais (DSP).
* **Conectividade:** Presença de dois PHYs Gigabit Ethernet integrados.
* **Modularidade:** Utiliza o formato/socket DDR2-SODIMM-200P, o que facilita imensamente a integração e o design de PCBs customizadas (placas-filhas/hats).
* **Pinagem Aberta:** O mapeamento da pinagem do SODIMM para o FPGA foi viabilizado através de engenharia reversa da comunidade.
* **Ecossistema Livre:** Possibilidade de programação, síntese e roteamento utilizando ferramentas 100% de software livre.

### Conversor Analógico-Digital (ADC)
O front-end de aquisição está sendo desenhado de forma modular, pois o ADC mais adequado depende das características do detector utilizado. Atualmente, o projeto está conduzindo estudos de viabilidade e testes de integração com os seguintes CIs:
* **AD9481:** 8 bits de resolução a 250 MSPS.
* **AD9248:** 14 bits de resolução a 65 MSPS.



## Gateware e Software

O código lógico (*gateware*) é desenvolvido utilizando as linguagens de descrição de hardware **Verilog** e **VHDL** e a compilação e roteamento para a FPGA são realizados utilizando a suíte de software livre **openxc7** (**Yosys** para síntese lógica, **NextPNR** para *place and route*, etc.).



## Licença

Para garantir que o conhecimento permaneça acessível e modificável pela comunidade, todo o material desenvolvido por este projeto (código-fonte, esquemáticos de hardware e documentação) é e sempre será licenciado sob a **GNU General Public License v3.0 (GPLv3)** ou superior.
