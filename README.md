# ha2azur

The goal of this project is to integrate a Cambridge Audio Azur 640R AV receiver with Home Assistant by using its RS-232 connector.

### Devices documentation

- [azur640r](docs/azur640r/): documentation for the AV Receiver Azur 640R itself from Cambridge Audio
- [pusr](docs/pusr/): documentation for the Serial to Ethernet USR-TCP232-302 from PUSR

### Serial communication parameters

Baud Rate：9600bps
Data Size：8bit
Parity：NONE
Stop Bits：1 bit
Local Port Number：4001
Remote Port Number：8234
Work Mode：TCP Server
Remote Server Addr：192.168.0.201
Client Overrun Mechanism：KEEP
Client Access Quantity：1