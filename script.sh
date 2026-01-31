# check if output.txt exists, if not create it

if [ ! -f output.txt ]; then
    touch output.txt
fi

echo "Hello, World!" >> output.txt