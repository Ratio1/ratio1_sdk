
cp ipfs.service /etc/systemd/system/ipfs.service
sudo systemctl daemon-reload
sudo systemctl enable ipfs
sudo systemctl start ipfs
./show.sh