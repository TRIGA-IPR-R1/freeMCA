# freeMCA ⚛️☢️🔬

**Um Analisador Multicanal (MCA) Totalmente Livre para Detectores de Radiação Ionizante.**

O `freeMCA` é um projeto de código e hardware livre que tem como objetivo projetar, construir e programar um Multi-Channel Analyzer (MCA) acessível para espectrometria de radiação, criando uma plataforma de pesquisa em instrumentação nuclear e desenvolvimento de produtos de baixo custo.

#### Status do Projeto

O `freeMCA` atualmente se encontra em fase de **Pesquisa e Prototipagem Ativa** (Work in Progress) e é um projeto de **pesquisa e desenvolvimento acadêmico** em instrumentação nuclear, do [Centro de Desenvolvimento da Tecnologia Nuclear (CDTN](https://www.gov.br/cdtn) - [CNEN)](https://www.gov.br/cnen).

## Hardware, Gateware e Software

### FPGA Base
Para o desenvolvimento inicial, o projeto utiliza o SoM (System on Module) [**Colorlight i9plus-v6.1**](https://github.com/wuxx/Colorlight-FPGA-Projects/blob/master/colorlight_i9plus_v6.1.md) (equipada com o FPGA Xilinx Artix-7 **XC7A50T-FGG484**). A escolha dessa plataforma baseia-se nas seguintes vantagens estratégicas:

* **Custo-Benefício:** Entrega alto poder de processamento lógico com um custo de aquisição muito baixo.
* **Recursos Lógicos:** Alta disponibilidade de pinos de I/O e células lógicas para processamento digital de sinais (DSP).
* **Conectividade:** Presença de dois PHYs Gigabit Ethernet integrados.
* **Modularidade:** Utiliza o formato/socket DDR2-SODIMM-200P, o que facilita imensamente a integração e o design de PCBs customizadas (placas-filhas/hats).
* **Pinagem Aberta:** O mapeamento da pinagem do SODIMM para o FPGA foi viabilizado através de engenharia reversa da comunidade.
* **Ecossistema Livre:** Possibilidade de programação, síntese e roteamento utilizando ferramentas 100% de software livre.

As seguintes alternativas SoM de engenharia reversa da Colorlight podem ser utilizadas:
* [**Colorlight_i9_v7.2**](https://github.com/wuxx/Colorlight-FPGA-Projects/blob/master/colorlight_i9_v7.2.md) (FPGA: Lattice ECP5 LFE5U-45F-6BG381C)
* [**Colorlight_i5_v6.0**](https://github.com/wuxx/Colorlight-FPGA-Projects) (FPGA: Lattice ECP5 LFE5U-25F-6BG381C)

E as seguintes alternativas SoM de desenvolvimento aberto pela comunidade (MuseLab) podem ser utilizadas:
* [**iCESugar_pro**](https://github.com/wuxx/icesugar-pro) (FPGA: Lattice ECP5 LFE5U-25F-6BG256C)
* [**iCESugar**](https://github.com/wuxx/icesugar) (FPGA: Lattice ECP5 iCE40UP5K-SG48)


### Conversor Analógico-Digital (ADC)
O front-end de aquisição está sendo desenhado de forma modular, pois o ADC mais adequado depende das características do detector utilizado. Atualmente, o projeto está conduzindo estudos de viabilidade e testes de integração com os seguintes CIs:
* [**KeYi_AD9248:**](https://item.taobao.com/item.htm?id=765597907964) 2 canais de 14 bits de resolução a 65 MSPS.
* [**KeYi_AD9245:**](https://item.taobao.com/item.htm?id=967921950787) 1 canal de 14 bits de resolução a 80 MSPS.
* [**KeYi_AD9481:**](https://item.taobao.com/item.htm?id=798227328346) 1 canal de 8 bits de resolução a 250 MSPS.


### Programação

O código lógico (*gateware*) é desenvolvido utilizando as linguagens de descrição de hardware **Verilog** e **VHDL** e a síntese e roteamento para a FPGA são realizados utilizando a suíte de software livre [**openxc7**](https://github.com/openxc7) ([**Yosys**](https://github.com/yosyshq/yosys) para síntese lógica, [**NextPNR**](https://github.com/YosysHQ/nextpnr) para *place and route*, etc.).


## DIY - Do it yourself

Inicialmente o `freeMCA` será desenvolvido seguindo a filosofia DIY (faça você mesmo) e modular, mas futuramente poderá ser concebida uma PCB mais compacta e otimizada para, por exemplo, ser integrada dentro do detector.

Dadas as várias possibilidades de SoM e ADC que podem ser utilizados para construir o `freeMCA`, a nomenclatura segue o padrão: freeMCA + categoria + SoM + ADC; Por exemplo:
* freeMCA-diy-Colorlight_i9plus_v6.1-KeYi_AD9245_80
* freeMCA-diy-Colorlight_i9_v7.2-KeYi_AD9248_65
* freeMCA-diy-Colorlight_i5_v6.0-KeYi_AD9481_250
* freeMCA-diy-iCESugar_pro-KeYi_AD9245_80
* freeMCA-diy-iCESugar-KeYi_AD9248_65

## Licença

Para garantir que o conhecimento permaneça acessível e modificável pela comunidade, todo o material desenvolvido por este projeto (código-fonte, esquemáticos de hardware e documentação) é e sempre será licenciado sob a [**GNU General Public License v3.0 (GPLv3)**](https://www.gnu.org/licenses/quick-guide-gplv3.html) ou superior.
